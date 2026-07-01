#!/usr/bin/env python3
"""Fit an empirical win-probability table from OpenDota parsed matches.

Only network caller for this pillar. OpenDota public API needs no key.
Writes engine/app/cache/winprob.json (win% by (game-minute, net-worth-lead) bucket).
"""
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from app.winprob import bucket_minute, bucket_lead, MINUTE_BUCKET, LEAD_BUCKET  # noqa: E402

CACHE = ROOT / "engine" / "app" / "cache" / "winprob.json"
API = "https://api.opendota.com/api"
MATCH_LIMIT = 100


def build_table(samples: list[tuple[int, int, bool]]) -> dict:
    buckets: dict = {}
    for clock_s, lead, win in samples:
        mb = str(bucket_minute(clock_s))
        lb = str(bucket_lead(lead))
        cell = buckets.setdefault(mb, {}).setdefault(lb, {"wins": 0, "total": 0})
        cell["total"] += 1
        if win:
            cell["wins"] += 1
    return {"minute_bucket": MINUTE_BUCKET, "lead_bucket": LEAD_BUCKET, "buckets": buckets}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "dota2-live-helper"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    try:
        pro = fetch_json(f"{API}/proMatches")
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"ERROR: could not reach OpenDota: {e}", file=sys.stderr)
        sys.exit(1)
    ids = [m["match_id"] for m in pro][:MATCH_LIMIT]
    samples: list[tuple[int, int, bool]] = []
    kept = 0
    for mid in ids:
        try:
            m = fetch_json(f"{API}/matches/{mid}")
        except (urllib.error.URLError, json.JSONDecodeError):
            continue
        adv = m.get("radiant_gold_adv")
        win = m.get("radiant_win")
        if not adv or win is None:
            continue
        kept += 1
        for minute, g in enumerate(adv):
            samples.append((minute * 60, int(g), bool(win)))
        time.sleep(1)  # be polite to the free API
    table = build_table(samples)
    table["generated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(table))
    print(f"Wrote {CACHE}: {kept} matches, {len(samples)} samples")


if __name__ == "__main__":
    main()
