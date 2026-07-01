#!/usr/bin/env python3
"""Refresh per-hero Herald win-rates from OpenDota heroStats.

ONLY network-caller for hero meta. One request to a single constant endpoint:
  GET /api/heroStats   ->  JSON array of 127 hero rows

Each row carries bracketed pub pick/win counters `1_pick`..`8_pick` and
`1_win`..`8_win`, where bracket 1 == Herald and bracket 8 == Immortal
(verified live 2026-07-01). Herald win-rate = 1_win / 1_pick.

Writes engine/app/cache/hero_meta.json (gitignored), keyed by GSI hero KEY
(npc_dota_hero_*) via engine/app/data/heroes.json id->key. The row's own
"name" field already equals that key, but we resolve through heroes.json so
the cache key set exactly matches the rest of the engine.

IMPORTANT: after running, RESTART the engine — HERO_META loads once at import;
the running server won't see the new cache until restart.

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
CACHE  = ROOT / "engine" / "app" / "cache" / "hero_meta.json"

OPENDOTA = "https://api.opendota.com/api"

# Bracket index -> name (OpenDota heroStats). Herald is bracket 1.
HERALD_BRACKET = 1


# ---------------------------------------------------------------------------
# Pure transform functions (unit-tested — NO network, NO I/O)
# ---------------------------------------------------------------------------

def bracket_winrate(row: dict, bracket: int = HERALD_BRACKET) -> float | None:
    """Win-rate for a single skill bracket from a heroStats row.

    Reads `<bracket>_win` / `<bracket>_pick`. Returns a float in [0, 1]
    rounded to 4 dp, or None when the bracket has no picks (avoids
    ZeroDivisionError; e.g. bracket 8/Immortal is frequently 0 in pub data).

    Missing keys are treated as 0 (degrade-safe against schema drift).
    """
    pick = row.get(f"{bracket}_pick") or 0
    win  = row.get(f"{bracket}_win") or 0
    if not pick:
        return None
    return round(win / pick, 4)


def transform_hero_meta_row(row: dict) -> dict | None:
    """One heroStats row -> a cache-ready hero-meta entry, or None to drop.

    Drops rows lacking a numeric `id`. The returned dict is bracket-agnostic
    at the schema level but currently only carries Herald figures.

    Returns:
        {"herald_winrate": float|None, "herald_pick": int, "herald_win": int}
    """
    if row.get("id") is None:
        return None
    return {
        "herald_winrate": bracket_winrate(row, HERALD_BRACKET),
        "herald_pick":    int(row.get(f"{HERALD_BRACKET}_pick") or 0),
        "herald_win":     int(row.get(f"{HERALD_BRACKET}_win") or 0),
    }


def transform_hero_stats(
    hero_stats: list[dict],
    id_to_key: dict[int, str],
) -> dict[str, dict]:
    """Transform the full heroStats array into a key-indexed meta dict.

    Rows whose numeric id is absent from `id_to_key` (heroes.json) are
    skipped — the cache key set stays a subset of the engine's hero keys.

    Args:
        hero_stats: raw /api/heroStats response (list of hero rows)
        id_to_key:  {numeric hero id -> "npc_dota_hero_*"} from heroes.json

    Returns:
        {hero_key: {"herald_winrate": ..., "herald_pick": ..., "herald_win": ...}}
    """
    out: dict[str, dict] = {}
    for row in hero_stats:
        entry = transform_hero_meta_row(row)
        if entry is None:
            continue
        key = id_to_key.get(int(row["id"]))
        if key is None:
            continue
        out[key] = entry
    return out


# ---------------------------------------------------------------------------
# Thin network wrapper (NOT unit-tested — network confined to scripts/)
# ---------------------------------------------------------------------------

_last_req_time: float = 0.0


def _get_json(url: str) -> object:
    """HTTP GET with ~1.1 s + jitter throttle and 429/521 back-off.

    Mirrors refresh_item_builds._get_json. A User-Agent header is REQUIRED —
    OpenDota returns 403 to urllib's default UA (verified 2026-07-01).
    """
    global _last_req_time
    elapsed = time.monotonic() - _last_req_time
    delay   = 1.1 + random.uniform(0, 0.15)
    if elapsed < delay:
        time.sleep(delay - elapsed)

    req = urllib.request.Request(url, headers={"User-Agent": "dota2-live-helper/1.0"})
    for _ in range(3):
        _last_req_time = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  429 rate-limit hit, sleeping 60 s…", file=sys.stderr)
                time.sleep(60)
            elif e.code == 521:
                print("  521 Cloudflare error, sleeping 30 s…", file=sys.stderr)
                time.sleep(30)
            else:
                raise
        except urllib.error.URLError:
            raise

    raise RuntimeError(f"gave up after 3 attempts on {url}")


def fetch_hero_stats() -> list[dict]:
    """GET /api/heroStats -> raw list of hero rows."""
    print("Fetching /api/heroStats …")
    return _get_json(f"{OPENDOTA}/heroStats")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    heroes = json.loads(HEROES.read_text())
    id_to_key = {int(h["id"]): h["key"] for h in heroes}

    try:
        hero_stats = fetch_hero_stats()
    except Exception as exc:
        print(f"FATAL: could not fetch heroStats: {exc}", file=sys.stderr)
        sys.exit(1)

    out_heroes = transform_hero_stats(hero_stats, id_to_key)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":  "opendota",
        "endpoint": "/api/heroStats",
        "bracket": f"herald({HERALD_BRACKET})",
        "heroes":  out_heroes,
    }
    CACHE.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {CACHE} ({len(out_heroes)}/{len(heroes)} heroes)")
    print("Remember to RESTART the engine — cache loads once at import.")


if __name__ == "__main__":
    main()
