#!/usr/bin/env python3
"""Refresh all-hero item builds + farm benchmarks from OpenDota.

Fetches two constant endpoints once, then for each of the 127 real hero ids
(from heroes.json — non-contiguous, never range(1,128)) hits:
  GET /api/heroes/{hid}/itemPopularity
  GET /api/benchmarks?hero_id={hid}

Writes engine/app/cache/item_builds.json (gitignored).

IMPORTANT: after running (~5 min: 127 heroes × 2 endpoints + 2 constants at
~1.1 s/req), RESTART the engine — ITEM_BUILDS loads once at import; the
running server won't see the new cache until restart.

Refresh cadence is per-patch, not per-game (meta is static).
"""
import datetime
import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[1]
HEROES = ROOT / "engine" / "app" / "data" / "heroes.json"
CACHE  = ROOT / "engine" / "app" / "cache" / "item_builds.json"

OPENDOTA = "https://api.opendota.com/api"

# ---------------------------------------------------------------------------
# Pure constants
# ---------------------------------------------------------------------------

CONSUMABLE_BLOCKLIST: set[str] = {
    "ward_observer",
    "ward_sentry",
    "tpscroll",
    "dust",
    "smoke_of_deceit",
    "tango",
    "clarity",
    "flask",
    "enchanted_mango",
    "faerie_fire",
    "branches",
}

PHASE_MAP: dict[str, str] = {
    "start_game_items": "start_game",
    "early_game_items": "early_game",
    "mid_game_items":   "mid_game",
    "late_game_items":  "late_game",
}

# ---------------------------------------------------------------------------
# Pure transform functions (unit-tested — NO network, NO I/O)
# ---------------------------------------------------------------------------

def component_part_keys(items: dict) -> set[str]:
    """Every item key that appears inside some other item's `components` list (i.e. is used as a buildup part)."""
    parts: set[str] = set()
    for meta in items.values():
        for comp in (meta.get("components") or []):
            parts.add(comp)
    return parts


def resolve_item(
    numeric_id: int,
    item_ids: dict[str, str],
    items: dict[str, dict],
    part_keys: set[str],
) -> dict | None:
    """Resolve a numeric item id to a cache-ready dict, or None if it should
    be dropped.

    Drops when (in order):
    - numeric_id not found in item_ids (str key lookup)
    - name not found in items constants
    - meta["dname"] is None (recipes / tokens)
    - name in CONSUMABLE_BLOCKLIST (wards, scrolls, stat branches, etc.)
    - meta.get("qual") == "consumable" (salve/clarity/etc.)
    - meta.get("components") is None AND name in part_keys  (structural rule:
      atomic buildup part — catches secret_shop/rare raw-stat sticks while
      keeping Blink Dagger which is atomic but used as part of nothing)

    Returns:
        {"id": int, "key": "item_<name>", "display": str}  on success
        None  on any drop condition
    """
    name = item_ids.get(str(numeric_id))
    if name is None:
        return None

    meta = items.get(name)
    if meta is None:
        return None

    dname = meta.get("dname")
    if dname is None:
        return None

    if name in CONSUMABLE_BLOCKLIST:
        return None

    if meta.get("qual") == "consumable":
        return None

    if meta.get("components") is None and name in part_keys:
        return None

    return {
        "id":      numeric_id,
        "key":     f"item_{name}",
        "display": dname,
    }


def transform_item_popularity(
    item_pop: dict,
    item_ids: dict[str, str],
    items: dict[str, dict],
    top_n: int = 8,
) -> dict[str, list[dict]]:
    """Transform OpenDota itemPopularity response into phase-keyed build lists.

    Phase-key translation: OpenDota returns `<phase>_items`; output uses
    `<phase>` (via PHASE_MAP).

    Cross-phase dedup: a global seen-set iterates phases start→early→mid→late;
    each item is kept only in the EARLIEST phase it appears.

    Each phase list is sorted descending by count, filtered (resolve_item),
    deduped, then capped at top_n. The returned dicts include a "count" field.

    Args:
        item_pop:  raw OpenDota itemPopularity dict {"<phase>_items": {"<id>": count}}
        item_ids:  /api/constants/item_ids response
        items:     /api/constants/items response
        top_n:     per-phase cap after filter+dedup (default 8)

    Returns:
        dict keyed by "start_game", "early_game", "mid_game", "late_game"
    """
    part_keys = component_part_keys(items)
    phase_order = [
        "start_game_items",
        "early_game_items",
        "mid_game_items",
        "late_game_items",
    ]
    seen: set[str] = set()
    result: dict[str, list[dict]] = {}

    for opendota_phase in phase_order:
        output_phase = PHASE_MAP[opendota_phase]
        raw: dict[str, int] = item_pop.get(opendota_phase, {})

        # Sort descending by count before resolving (preserves order; count
        # is cast to int from str keys just in case)
        sorted_ids = sorted(
            ((int(id_str), int(count)) for id_str, count in raw.items()),
            key=lambda x: x[1],
            reverse=True,
        )

        phase_items: list[dict] = []
        for numeric_id, count in sorted_ids:
            if len(phase_items) >= top_n:
                break
            resolved = resolve_item(numeric_id, item_ids, items, part_keys)
            if resolved is None:
                continue
            item_key = resolved["key"]
            if item_key in seen:
                continue
            seen.add(item_key)
            phase_items.append({**resolved, "count": count})

        result[output_phase] = phase_items

    return result


def transform_benchmarks(bench_result: dict) -> dict:
    """Extract the four ascending benchmark arrays from OpenDota benchmarks.

    OpenDota returns:
        {
          "gold_per_min":      [{"percentile": 0.1, "value": 312}, ...],
          "xp_per_min":        [...],
          "last_hits_per_min": [...],
          "hero_damage_per_min": [...]   # DROPPED (YAGNI)
        }

    Returns a flat dict with parallel arrays:
        {
          "percentiles":       [0.1, 0.2, ...],
          "gold_per_min":      [312, 378, ...],
          "xp_per_min":        [402, 468, ...],
          "last_hits_per_min": [3.1, 4.0, ...]
        }
    """
    # Anchor on gold_per_min to extract percentile spine
    gpm_rows = bench_result.get("gold_per_min", [])
    percentiles = [row["percentile"] for row in gpm_rows]

    def _extract(key: str) -> list:
        rows = bench_result.get(key, [])
        return [row["value"] for row in rows]

    return {
        "percentiles":       percentiles,
        "gold_per_min":      _extract("gold_per_min"),
        "xp_per_min":        _extract("xp_per_min"),
        "last_hits_per_min": _extract("last_hits_per_min"),
    }


def build_hero_entry(
    hero: str,
    item_pop: dict,
    bench_result: dict,
    item_ids: dict[str, str],
    items: dict[str, dict],
    hero_display: str = "",
    hero_id: int | None = None,
) -> dict:
    """Assemble the full per-hero cache entry dict.

    Pure — no I/O, no timestamp (timestamp is added by main()).

    Args:
        hero:         GSI hero key, e.g. "npc_dota_hero_juggernaut"
        item_pop:     raw OpenDota itemPopularity response
        bench_result: raw OpenDota benchmarks result object
        item_ids:     /api/constants/item_ids
        items:        /api/constants/items
        hero_display: human-readable name from heroes.json (e.g. "Juggernaut")
        hero_id:      numeric hero id from heroes.json
    """
    builds     = transform_item_popularity(item_pop, item_ids, items)
    benchmarks = transform_benchmarks(bench_result)

    return {
        "hero_id":    hero_id,
        "display":    hero_display,
        "builds":     builds,
        "benchmarks": benchmarks,
    }


# ---------------------------------------------------------------------------
# Thin network wrappers (NOT unit-tested — network confined to scripts/)
# ---------------------------------------------------------------------------

_last_req_time: float = 0.0


def _get_json(url: str) -> dict:
    """HTTP GET with ~1.1 s + jitter throttle and 429/521 back-off.

    Throttle is global-state based; this script is single-threaded.
    Back-off: 60 s on 429, 30 s on Cloudflare 521. Other HTTP errors
    are fatal.
    """
    global _last_req_time
    elapsed = time.monotonic() - _last_req_time
    delay   = 1.1 + random.uniform(0, 0.15)
    if elapsed < delay:
        time.sleep(delay - elapsed)

    req = urllib.request.Request(url, headers={"User-Agent": "dota2-live-helper/1.0"})
    for attempt in range(3):
        _last_req_time = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  429 rate-limit hit, sleeping 60 s…", file=sys.stderr)
                time.sleep(60)
            elif e.code == 521:
                print(f"  521 Cloudflare error, sleeping 30 s…", file=sys.stderr)
                time.sleep(30)
            else:
                raise
        except urllib.error.URLError:
            raise

    raise RuntimeError(f"gave up after 3 attempts on {url}")


def fetch_constants() -> tuple[dict, dict]:
    """Fetch /api/constants/item_ids and /api/constants/items once up front.

    Returns:
        (item_ids, items) — both raw dicts from OpenDota
    """
    print("Fetching /api/constants/item_ids …")
    item_ids = _get_json(f"{OPENDOTA}/constants/item_ids")
    print("Fetching /api/constants/items …")
    items = _get_json(f"{OPENDOTA}/constants/items")
    return item_ids, items


def fetch_item_popularity(hid: int) -> dict:
    """GET /api/heroes/{hid}/itemPopularity → raw response dict."""
    return _get_json(f"{OPENDOTA}/heroes/{hid}/itemPopularity")


def fetch_benchmarks(hid: int) -> dict:
    """GET /api/benchmarks?hero_id={hid} → raw response dict (has "result" key)."""
    return _get_json(f"{OPENDOTA}/benchmarks?hero_id={hid}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    heroes = json.loads(HEROES.read_text())
    # Real hero ids from heroes.json — non-contiguous (never range(1, 128))
    hero_list = [(h["id"], h["key"], h["display"]) for h in heroes]

    try:
        item_ids, items = fetch_constants()
    except Exception as exc:
        print(f"FATAL: could not fetch constants (item_ids/items required): {exc}",
              file=sys.stderr)
        sys.exit(1)

    out_heroes: dict[str, dict] = {}
    total = len(hero_list)

    for i, (hid, hero_key, hero_display) in enumerate(hero_list, 1):
        print(f"[{i}/{total}] {hero_key} (id={hid})")
        try:
            item_pop    = fetch_item_popularity(hid)
            bench_resp  = fetch_benchmarks(hid)
            bench_result = bench_resp.get("result", {})

            entry = build_hero_entry(
                hero        = hero_key,
                item_pop    = item_pop,
                bench_result= bench_result,
                item_ids    = item_ids,
                items       = items,
                hero_display= hero_display,
                hero_id     = hid,
            )
            out_heroes[hero_key] = entry
            print(f"  ✓ {hero_display}")
        except (KeyError, ValueError, TypeError,
                urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"  skip hero {hero_key}: {exc}", file=sys.stderr)
            continue

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "opendota",
        "note":   "un-bracketed all-MMR aggregate",
        "heroes": out_heroes,
    }
    CACHE.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {CACHE} ({len(out_heroes)}/{total} heroes)")
    print("Remember to RESTART the engine — cache loads once at import.")


if __name__ == "__main__":
    main()
