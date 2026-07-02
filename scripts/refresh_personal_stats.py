#!/usr/bin/env python3
"""Refresh YOUR personal win-rates (per-hero + per-item-per-hero) from OpenDota.

Two things, both keyless (OpenDota needs no API key):

  1. Per-hero win-rate — one call to GET /api/players/{id}/heroes gives games +
     wins for every hero you have ever played. All-time, cheap.

  2. Per-item-per-hero win-rate — the match LIST carries no items, so we walk
     your match history (GET /api/players/{id}/matches), and for each match not
     already processed fetch GET /api/matches/{match_id} once to read your final
     inventory, mapping each item id -> key and tallying wins per (hero, item).

The item half is the slow, rate-limited half (~1.1 s/request). It is therefore
INCREMENTAL and RESUMABLE: processed match ids + running games/wins are saved to
the cache every 25 matches, so a rate-limit stall or Ctrl-C loses nothing — just
re-run and it picks up where it stopped.

account_id resolution order: --account-id  ->  $DOTA_ACCOUNT_ID  ->  the running
engine's GET /whoami (auto-captured from live GSI). If none resolve, we explain
how to set it and exit.

Writes engine/app/cache/personal_stats.json (gitignored).

IMPORTANT: after running, RESTART the engine — PERSONAL_STATS loads once at
import; the running server won't see the new cache until restart.

NOTE: OpenDota only has your history if your Dota profile has "Expose Public
Match Data" enabled (Settings -> Advanced Options). Without it /players/{id}/...
comes back empty and this writes an empty cache.
"""
import argparse
import datetime
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[1]
HEROES = ROOT / "engine" / "app" / "data" / "heroes.json"
CACHE  = ROOT / "engine" / "app" / "cache" / "personal_stats.json"

OPENDOTA = "https://api.opendota.com/api"
DEFAULT_ENGINE_URL = "http://127.0.0.1:3939"

# Final-inventory slots we read per match: the 6 main slots only.
# Backpack is deliberately excluded — it is mostly consumables / overflow and
# would add noise to "the items you finished the game with". item_neutral is
# excluded too: neutral ids never appear in OpenDota itemPopularity buckets nor
# any curated build, so a per-hero neutral cell can never surface on a build
# chip — including it only bloats the cache with highly-variable neutral picks.
ITEM_SLOTS: list[str] = [f"item_{i}" for i in range(6)]

# Non-build junk to drop from a final inventory (wards, scrolls, stat sticks).
# Mirrors refresh_item_builds.CONSUMABLE_BLOCKLIST; qual=="consumable" from the
# items constant catches the rest (salves/clarities/etc.).
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


# ---------------------------------------------------------------------------
# Pure transform functions (unit-tested — NO network, NO I/O)
# ---------------------------------------------------------------------------

def won_from_slot(player_slot: int, radiant_win: bool) -> bool:
    """True iff the player on `player_slot` was on the winning side.

    Dota player_slot < 128 == Radiant. Robust to anonymised account ids
    (we never rely on account_id to decide the result).
    """
    is_radiant = player_slot < 128
    return bool(is_radiant == radiant_win)


def transform_player_heroes(
    rows: list[dict],
    id_to_key: dict[int, str],
) -> dict[str, dict]:
    """`/players/{id}/heroes` rows -> {hero_key: {games, wins, winrate, last_played}}.

    Rows for hero ids absent from heroes.json, or with zero games, are skipped.
    winrate is win/games rounded to 4 dp.
    """
    out: dict[str, dict] = {}
    for r in rows:
        hid = r.get("hero_id")
        if hid is None:
            continue
        try:
            key = id_to_key.get(int(hid))
        except (TypeError, ValueError):
            continue
        if key is None:
            continue
        games = int(r.get("games") or 0)
        if games <= 0:
            continue
        wins = int(r.get("win") or 0)
        out[key] = {
            "games": games,
            "wins": wins,
            "winrate": round(wins / games, 4),
            "last_played": r.get("last_played"),
        }
    return out


def find_player(match: dict, player_slot: int, hero_id: int | None = None) -> dict | None:
    """Locate our player row inside a full /matches/{id} response.

    Prefer the exact player_slot (stable even when account_id is anonymised);
    fall back to hero_id when the slot is somehow absent.
    """
    players = match.get("players") or []
    for p in players:
        if p.get("player_slot") == player_slot:
            return p
    # Slot absent (rare, anonymised responses) — fall back to hero_id ONLY when
    # it is unambiguous. In a mirror match the same hero_id sits on both teams,
    # so guessing could return the ENEMY's row and tally their items against our
    # win/loss. If the hero appears more than once, refuse to guess.
    if hero_id is not None:
        same_hero = [p for p in players if p.get("hero_id") == hero_id]
        if len(same_hero) == 1:
            return same_hero[0]
    return None


def extract_item_keys(
    player: dict,
    item_ids: dict[str, str],
    items: dict[str, dict],
) -> list[str]:
    """A player's final inventory -> deduped list of build item keys.

    Reads item_0..5 + item_neutral, maps numeric id -> name via item_ids, drops
    empty slots (id 0/None), unknown ids, recipe/token entries (dname None),
    the consumable blocklist, and qual=="consumable". Returns "item_<name>"
    keys in slot order, de-duplicated.
    """
    out: list[str] = []
    seen: set[str] = set()
    for slot in ITEM_SLOTS:
        nid = player.get(slot)
        if not nid:  # None or 0 (empty slot)
            continue
        name = item_ids.get(str(nid))
        if name is None:
            continue
        meta = items.get(name) or {}
        if meta.get("dname") is None:
            continue
        if name in CONSUMABLE_BLOCKLIST:
            continue
        if meta.get("qual") == "consumable":
            continue
        key = f"item_{name}"
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def add_match_items(
    item_agg: dict[str, dict[str, dict]],
    hero_key: str,
    item_keys: list[str],
    won: bool,
) -> None:
    """Fold one match's (hero, items, result) into the running aggregate.

    item_agg[hero_key][item_key] = {"games": int, "wins": int} (mutated).
    """
    bucket = item_agg.setdefault(hero_key, {})
    for k in item_keys:
        e = bucket.setdefault(k, {"games": 0, "wins": 0})
        e["games"] += 1
        if won:
            e["wins"] += 1


def finalize_item_agg(
    item_agg: dict[str, dict[str, dict]],
    min_games: int = 1,
) -> dict[str, dict]:
    """Add a winrate to every (hero, item) cell, dropping cells below min_games."""
    out: dict[str, dict] = {}
    for hero_key, items in item_agg.items():
        hero_out: dict[str, dict] = {}
        for item_key, e in items.items():
            g = int(e.get("games") or 0)
            if g < min_games:
                continue
            w = int(e.get("wins") or 0)
            hero_out[item_key] = {
                "games": g,
                "wins": w,
                "winrate": round(w / g, 4) if g else None,
            }
        if hero_out:
            out[hero_key] = hero_out
    return out


def build_payload(
    account_id: int | None,
    hero_stats: dict[str, dict],
    item_agg: dict[str, dict[str, dict]],
    processed_ids,
    generated_at: str,
) -> dict:
    """Assemble the cache dict (winrate computed for hero + item halves)."""
    return {
        "generated_at": generated_at,
        "source": "opendota",
        "account_id": account_id,
        "heroes": hero_stats,
        "items": finalize_item_agg(item_agg),
        "processed_match_ids": sorted(int(m) for m in processed_ids),
    }


def item_agg_from_payload(data: dict) -> dict[str, dict[str, dict]]:
    """Rebuild the running games/wins aggregate from a saved cache (for resume)."""
    agg: dict[str, dict[str, dict]] = {}
    for hero_key, items in (data.get("items") or {}).items():
        agg[hero_key] = {
            item_key: {"games": int(v.get("games") or 0), "wins": int(v.get("wins") or 0)}
            for item_key, v in items.items()
        }
    return agg


# ---------------------------------------------------------------------------
# Thin network wrapper (NOT unit-tested — network confined to scripts/)
# ---------------------------------------------------------------------------

_last_req_time: float = 0.0


def _get_json(url: str) -> object:
    """OpenDota GET with ~1.1 s + jitter throttle and 429/521 back-off.

    Mirrors refresh_item_builds._get_json. A User-Agent header is REQUIRED —
    OpenDota returns 403 to urllib's default UA.
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


def _whoami(engine_url: str) -> int | None:
    """Ask the running engine for the live-captured account id (best effort)."""
    try:
        req = urllib.request.Request(
            engine_url.rstrip("/") + "/whoami",
            headers={"User-Agent": "dota2-live-helper/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        acc = data.get("account_id")
        return int(acc) if acc else None
    except Exception:
        return None


def resolve_account_id(args) -> int | None:
    if args.account_id:
        return int(args.account_id)
    env = os.environ.get("DOTA_ACCOUNT_ID")
    if env:
        return int(env)
    return _whoami(args.engine_url)


def fetch_constants() -> tuple[dict, dict]:
    print("Fetching /api/constants/item_ids …")
    item_ids = _get_json(f"{OPENDOTA}/constants/item_ids")
    print("Fetching /api/constants/items …")
    items = _get_json(f"{OPENDOTA}/constants/items")
    return item_ids, items


def _save(account_id, hero_stats, item_agg, processed) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(
        account_id, hero_stats, item_agg, processed,
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    CACHE.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--account-id", type=int, default=None,
                    help="Your 32-bit Dota account id (overrides env / engine).")
    ap.add_argument("--engine-url", default=DEFAULT_ENGINE_URL,
                    help="Running engine base URL for /whoami auto-detect.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap matches processed THIS run (default: all unprocessed).")
    args = ap.parse_args()

    account_id = resolve_account_id(args)
    if not account_id:
        print("FATAL: no account id. Pass --account-id, set $DOTA_ACCOUNT_ID, or\n"
              "       play/spectate one game so the engine can auto-capture it,\n"
              "       then re-run (the engine exposes it at /whoami).",
              file=sys.stderr)
        sys.exit(1)
    print(f"Account id: {account_id}")

    heroes = json.loads(HEROES.read_text())
    id_to_key = {int(h["id"]): h["key"] for h in heroes}

    try:
        item_ids, items = fetch_constants()
    except Exception as exc:
        print(f"FATAL: could not fetch item constants: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Feature A: per-hero win-rate (all-time, one call) -----------------
    print("Fetching /api/players/%d/heroes …" % account_id)
    hero_rows = _get_json(f"{OPENDOTA}/players/{account_id}/heroes")
    if not isinstance(hero_rows, list):
        hero_rows = []
    hero_stats = transform_player_heroes(hero_rows, id_to_key)
    print(f"  {len(hero_stats)} heroes played.")

    # --- Feature B: per-item-per-hero win-rate (incremental) ---------------
    print("Fetching /api/players/%d/matches …" % account_id)
    matches = _get_json(f"{OPENDOTA}/players/{account_id}/matches")
    if not isinstance(matches, list):
        matches = []
    print(f"  {len(matches)} matches in history.")

    processed: set[int] = set()
    item_agg: dict[str, dict[str, dict]] = {}
    if CACHE.exists():
        try:
            existing = json.loads(CACHE.read_text())
            processed = set(int(m) for m in existing.get("processed_match_ids", []))
            item_agg = item_agg_from_payload(existing)
            print(f"  resuming: {len(processed)} matches already processed.")
        except Exception:
            processed, item_agg = set(), {}

    todo = [m for m in matches if int(m.get("match_id", -1)) not in processed]
    if args.limit is not None:
        todo = todo[: args.limit]
    total = len(todo)
    print(f"  {total} matches to fetch this run.")

    for i, m in enumerate(todo, 1):
        mid = int(m.get("match_id", -1))
        slot = m.get("player_slot")
        hid = m.get("hero_id")
        rwin = m.get("radiant_win")
        hero_key = id_to_key.get(int(hid)) if hid is not None else None
        # A None hero_key (hero not yet in heroes.json) or None radiant_win
        # (unparsed / very recent match) is CHEAP to retry — no /matches call is
        # made — and self-heals once heroes.json is updated or the match parses.
        # So we only mark such matches processed AFTER the guard passes; otherwise
        # they would be lost forever the first time we skipped them.
        guard_ok = slot is not None and rwin is not None and hero_key is not None
        try:
            if guard_ok:
                match = _get_json(f"{OPENDOTA}/matches/{mid}")
                player = find_player(match, slot, hid)
                if player is not None:
                    keys = extract_item_keys(player, item_ids, items)
                    add_match_items(item_agg, hero_key, keys, won_from_slot(slot, rwin))
        except urllib.error.HTTPError as e:
            print(f"  match {mid}: HTTP {e.code}, skipping", file=sys.stderr)
        if guard_ok:
            processed.add(mid)

        if i % 25 == 0:
            _save(account_id, hero_stats, item_agg, processed)
            print(f"  …{i}/{total} (saved)")

    _save(account_id, hero_stats, item_agg, processed)
    n_items = sum(len(v) for v in finalize_item_agg(item_agg).values())
    print(f"\nWrote {CACHE}")
    print(f"  {len(hero_stats)} heroes, {n_items} (hero,item) cells, "
          f"{len(processed)} matches processed.")
    print("Remember to RESTART the engine — cache loads once at import.")


if __name__ == "__main__":
    main()
