#!/usr/bin/env python3
"""Analyze a parsed OpenDota match into a cached win-prob review report.

Only network caller. OpenDota public API needs no key. The match must be PARSED
(radiant_gold_adv present); if not, this requests a parse and asks you to re-run.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from app.winprob import win_probability, load_winprob  # noqa: E402
from app.reviews import REVIEWS_DIR  # noqa: E402

API = "https://api.opendota.com/api"
_THRESHOLD = 0.12


def _label_moment(match: dict, minute: int, is_radiant: bool) -> str:
    t = minute * 60
    labels: list[str] = []
    for o in match.get("objectives") or []:
        ot = o.get("time")
        if ot is None or abs(ot - t) > 60:
            continue
        typ = (o.get("type") or "").upper()
        if "ROSHAN" in typ:
            labels.append("Roshan")
        elif "TOWER" in typ or "BUILDING" in typ:
            labels.append("tower")
        elif "AEGIS" in typ:
            labels.append("aegis")
    for tf in match.get("teamfights") or []:
        start, end = tf.get("start"), tf.get("end")
        if start is None or end is None:
            continue
        if start - 60 <= t <= end + 60:
            deaths = tf.get("deaths")
            labels.append(f"teamfight ({deaths} deaths)" if deaths is not None else "teamfight")
    return " / ".join(dict.fromkeys(labels)) if labels else "big swing"


def analyze(match: dict, account_id: int | None, table: dict | None) -> dict:
    players = match.get("players") or []
    is_radiant = True
    your_side = "radiant"
    note = None
    me = None
    if account_id is not None:
        me = next((p for p in players if p.get("account_id") == account_id), None)
    if me is not None:
        is_radiant = bool(me.get("isRadiant"))
        your_side = "radiant" if is_radiant else "dire"
    else:
        note = "account_id not found; showing radiant perspective"

    radiant_win = match.get("radiant_win")
    you_won = None if radiant_win is None else (radiant_win if is_radiant else not radiant_win)
    sign = 1 if is_radiant else -1

    curve = []
    for minute, g in enumerate(match.get("radiant_gold_adv") or []):
        lead = sign * int(g)
        curve.append({"minute": minute, "lead": lead,
                      "win_prob": round(win_probability(lead, minute * 60, table), 4)})

    moments = []
    for i in range(1, len(curve)):
        delta = round(curve[i]["win_prob"] - curve[i - 1]["win_prob"], 4)
        if abs(delta) >= _THRESHOLD:
            prior = curve[i - 1]["win_prob"]
            kind = "threw" if (delta < 0 and prior > 0.6) else ("gain" if delta > 0 else "swing")
            moments.append({
                "minute": curve[i]["minute"], "delta": delta, "win_prob": curve[i]["win_prob"],
                "kind": kind, "label": _label_moment(match, curve[i]["minute"], is_radiant),
            })

    peak = max(curve, key=lambda c: c["win_prob"]) if curve else {"win_prob": None, "minute": None}
    biggest = max(moments, key=lambda m: abs(m["delta"]))["minute"] if moments else None
    report = {
        "match_id": match.get("match_id"), "your_side": your_side, "you_won": you_won,
        "duration_s": match.get("duration"), "curve": curve, "moments": moments,
        "summary": {
            "peak_win_prob": peak["win_prob"], "peak_minute": peak["minute"],
            "threw_count": sum(1 for m in moments if m["kind"] == "threw"),
            "biggest_swing_min": biggest,
        },
    }
    if note:
        report["note"] = note
    return report


def fetch_json(url: str, method: str = "GET"):
    req = urllib.request.Request(url, headers={"User-Agent": "dota2-live-helper"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("match_id", type=int)
    ap.add_argument("--account-id", type=int, default=None)
    args = ap.parse_args()
    account_id = args.account_id
    if account_id is None and os.environ.get("DOTA_ACCOUNT_ID"):
        account_id = int(os.environ["DOTA_ACCOUNT_ID"])

    try:
        match = fetch_json(f"{API}/matches/{args.match_id}")
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"ERROR: could not fetch match: {e}", file=sys.stderr)
        sys.exit(1)

    if not match.get("radiant_gold_adv"):
        try:
            fetch_json(f"{API}/request/{args.match_id}", method="POST")
        except (urllib.error.URLError, json.JSONDecodeError):
            pass
        print("Match not parsed yet — requested a parse. Re-run in ~2 minutes.")
        sys.exit(0)

    report = analyze(match, account_id, load_winprob())
    report["generated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = REVIEWS_DIR / f"{args.match_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report))
    print(f"Wrote {out} ({len(report['curve'])} minutes, {len(report['moments'])} moments)")


if __name__ == "__main__":
    main()
