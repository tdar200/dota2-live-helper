#!/usr/bin/env python3
"""Refresh Herald counter/synergy data from Stratz into engine/app/cache/matchups.json.

Only network caller in the project. Needs env STRATZ_API_KEY (free key from stratz.com).
Schema: verify against https://api.stratz.com/graphiql if Stratz changes field names.
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEROES = ROOT / "engine" / "app" / "data" / "heroes.json"
BUILDS = ROOT / "engine" / "app" / "data" / "builds"
CACHE = ROOT / "engine" / "app" / "cache" / "matchups.json"
STRATZ_URL = "https://api.stratz.com/graphql"


def transform_matchup(matchup: dict, id_to_key: dict[int, str]) -> dict:
    def conv(rows):
        out = {}
        for r in rows or []:
            mc = r.get("matchCount", 0)
            key = id_to_key.get(r.get("heroId2"))
            if mc and key:
                out[key] = round(r.get("winCount", 0) / mc, 4)
        return out
    return {"vs": conv(matchup.get("vs")), "with": conv(matchup.get("with"))}


def build_query(hero_id: int) -> tuple[str, dict]:
    query = """
    query M($h: Short!) {
      heroStats {
        matchUp(heroId: $h, take: 300, bracketBasicIds: [HERALD]) {
          heroId
          vs { heroId2 winCount matchCount }
          with { heroId2 winCount matchCount }
        }
      }
    }"""
    return query, {"h": hero_id}


def fetch_matchup(hero_id: int, api_key: str) -> dict:
    query, variables = build_query(hero_id)
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        STRATZ_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "STRATZ_API",  # Stratz requires a UA
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR: Stratz HTTP {e.code} for hero {hero_id} "
              f"({'bad/expired STRATZ_API_KEY' if e.code == 401 else 'rate limit' if e.code == 429 else 'server error'})",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach Stratz: {e.reason}", file=sys.stderr)
        sys.exit(1)
    if data.get("errors"):
        print(f"ERROR: Stratz GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(1)
    matchups = data["data"]["heroStats"]["matchUp"]
    return matchups[0] if matchups else {"vs": [], "with": []}


def main() -> None:
    api_key = os.environ.get("STRATZ_API_KEY")
    if not api_key:
        print("ERROR: set STRATZ_API_KEY (free key from stratz.com)", file=sys.stderr)
        sys.exit(1)
    heroes = json.loads(HEROES.read_text())
    key_to_id = {h["key"]: h["id"] for h in heroes}
    id_to_key = {h["id"]: h["key"] for h in heroes}
    pocket = [p.stem for p in sorted(BUILDS.glob("*.json"))]  # file stems, e.g. "skeleton_king"
    # map file stem -> hero key via display/build hero field
    pocket_keys = []
    for stem in pocket:
        build = json.loads((BUILDS / f"{stem}.json").read_text())
        pocket_keys.append(build["hero"])

    out_heroes = {}
    for hero_key in pocket_keys:
        hero_id = key_to_id.get(hero_key)
        if hero_id is None:
            print(f"  ! no id for {hero_key}, skipping", file=sys.stderr)
            continue
        matchup = fetch_matchup(hero_id, api_key)
        out_heroes[hero_key] = transform_matchup(matchup, id_to_key)
        print(f"  ✓ {hero_key}")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(
        {"bracket": "HERALD", "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(), "heroes": out_heroes}, indent=2))
    print(f"Wrote {CACHE} ({len(out_heroes)} heroes)")


if __name__ == "__main__":
    main()
