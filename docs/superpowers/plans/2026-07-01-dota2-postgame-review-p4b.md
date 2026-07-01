# Dota 2 Live Helper — P4b Post-Game Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add post-game review — a script analyzes a parsed OpenDota match into a cached win-prob-curve + key-moments report, the keyless engine serves it, and a dashboard "Review" tab renders it.

**Architecture:** `review_match.py` (only network caller) fetches a parsed match, runs a pure `analyze()` that reuses P4a's `win_probability` over the per-minute net-worth advantage (from the player's perspective), and writes `cache/reviews/<id>.json`. `reviews.py` serves reports offline via `GET /review/{id}` and `GET /reviews`. The dashboard gains a `Live | Review` toggle whose Review tab renders an inline-SVG win% chart + moments.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest (engine); Vite + vanilla JS (dashboard). Script uses stdlib `urllib` (no new deps).

## Global Constraints

- **VAC-safe & keyless engine:** the engine/tests NEVER call the network. Only `scripts/review_match.py` calls OpenDota (no key). Reports load from the gitignored `engine/app/cache/reviews/`.
- **Offline tests:** no test performs a live network call. The pure `analyze()` is tested on a synthetic match fixture.
- **Reuse P4a:** the win% curve uses `app.winprob.win_probability(lead, minute*60, table)` with `load_winprob()` (empirical table if fitted, else logistic fallback).
- **Perspective:** orient the net-worth lead to the user's side (`radiant_gold_adv` is radiant-signed; negate for Dire). `account_id` via `--account-id` or env `DOTA_ACCOUNT_ID`; absent → radiant perspective + a `note`.
- **Robust core, best-effort labels:** the curve + swings need only `radiant_gold_adv`/`radiant_win`/`players`; moment *labels* from `objectives`/`teamfights` degrade gracefully to `"big swing"` when absent.
- **Moment threshold:** consecutive-minute win% `abs(delta) >= 0.12`. `kind="threw"` when `delta<0` and prior win% > 0.6; `"gain"` when `delta>0`; else `"swing"`.
- **Display-agnostic engine:** `reviews.py` is pure file I/O over the cache; `main.py` is the only HTTP layer; the static mount stays LAST.
- **Pydantic v2 / Python 3.11+.** **Run pytest from `engine/` via `.venv/bin/python`.** Post-P4a suite is 46 tests; must stay green.
- **Project root:** `/home/tahseen-dar/Projects/dota2-live-helper`.

---

## File Structure

```
engine/app/
  reviews.py                 # load_review() / list_reviews() over cache/reviews/
  cache/reviews/<id>.json    # gitignored, written by the review script
  main.py                    # + GET /review/{match_id}, GET /reviews
scripts/review_match.py      # OpenDota fetch + pure analyze() (only network caller)
engine/tests/
  test_reviews.py
  test_review_analyze.py
dashboard/src/
  panels/review.js           # renderReview() + populateReviews() + inline-SVG chart
  main.js, index.html, style.css   # Live|Review toggle + review view
```

---

### Task 1: `reviews.py` loader + `GET /review/{match_id}` + `GET /reviews`

**Files:**
- Create: `engine/app/reviews.py`
- Modify: `engine/app/main.py`
- Test: `engine/tests/test_reviews.py`

**Interfaces:**
- Produces (in `app.reviews`):
  - `REVIEWS_DIR: Path` (= `engine/app/cache/reviews`).
  - `load_review(match_id: int, dir: Path = REVIEWS_DIR) -> dict | None` — reads `<dir>/<match_id>.json` or None.
  - `list_reviews(dir: Path = REVIEWS_DIR) -> list[dict]` — one `{match_id, your_side, you_won, duration_s}` per report; `[]` when the dir is absent.
  - `main.py`: `GET /review/{match_id}` (404 when absent, report JSON when present); `GET /reviews` (the list).

- [ ] **Step 1: Write the failing tests**

`engine/tests/test_reviews.py`:
```python
import json
from fastapi.testclient import TestClient
from app.reviews import load_review, list_reviews
from app.main import app


def test_load_review_missing(tmp_path):
    assert load_review(123, dir=tmp_path) is None


def test_load_review_present(tmp_path):
    (tmp_path / "7.json").write_text(json.dumps({"match_id": 7, "you_won": True}))
    assert load_review(7, dir=tmp_path)["match_id"] == 7


def test_list_reviews_absent_dir_is_empty(tmp_path):
    assert list_reviews(dir=tmp_path / "nope") == []


def test_list_reviews_metadata(tmp_path):
    (tmp_path / "7.json").write_text(json.dumps(
        {"match_id": 7, "your_side": "radiant", "you_won": True, "duration_s": 2400, "curve": []}))
    assert list_reviews(dir=tmp_path) == [
        {"match_id": 7, "your_side": "radiant", "you_won": True, "duration_s": 2400}]


def test_review_endpoint_404_when_absent():
    assert TestClient(app).get("/review/999999999").status_code == 404


def test_reviews_endpoint_returns_list():
    resp = TestClient(app).get("/reviews")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_reviews.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.reviews'`.

- [ ] **Step 3: Implement `reviews.py`**

`engine/app/reviews.py`:
```python
import json
from pathlib import Path

REVIEWS_DIR = Path(__file__).parent / "cache" / "reviews"


def load_review(match_id: int, dir: Path = REVIEWS_DIR) -> dict | None:
    path = dir / f"{match_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_reviews(dir: Path = REVIEWS_DIR) -> list[dict]:
    if not dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(dir.glob("*.json")):
        try:
            r = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "match_id": r.get("match_id"),
            "your_side": r.get("your_side"),
            "you_won": r.get("you_won"),
            "duration_s": r.get("duration_s"),
        })
    return out
```

- [ ] **Step 4: Add the endpoints to `main.py`**

In `engine/app/main.py`, change the FastAPI import line to add `HTTPException`:
```python
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
```
Add near the other imports:
```python
from app.reviews import load_review, list_reviews
```
Add these routes immediately AFTER the `/roshan` handler and BEFORE the `if _DIST.exists():` static mount:
```python
@app.get("/review/{match_id}")
async def review(match_id: int) -> dict:
    report = load_review(match_id)
    if report is None:
        raise HTTPException(status_code=404, detail="not analyzed")
    return report


@app.get("/reviews")
async def reviews() -> list[dict]:
    return list_reviews()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_reviews.py -v`
Expected: PASS (6 passed). Then full suite: `.venv/bin/python -m pytest tests -q` — all green.

- [ ] **Step 6: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/reviews.py engine/app/main.py engine/tests/test_reviews.py
git commit -m "feat(engine): review report loader + /review and /reviews endpoints"
```

---

### Task 2: `review_match.py` — OpenDota fetch + pure `analyze()`

**Files:**
- Create: `scripts/review_match.py`
- Test: `engine/tests/test_review_analyze.py`

**Interfaces:**
- Produces (in `scripts/review_match.py`, importable for the analyze test):
  - `analyze(match: dict, account_id: int | None, table: dict | None) -> dict` — the report dict (curve/moments/summary/your_side/you_won), pure.
  - `_label_moment(match, minute, is_radiant) -> str`, `fetch_json(url)`, `main()` (network — not unit-tested).

- [ ] **Step 1: Write the failing analyze test**

`engine/tests/test_review_analyze.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from review_match import analyze


def _match():
    # radiant pulls ahead to +10k by minute 3, then a swing down at minute 4
    return {
        "match_id": 42,
        "radiant_win": True,
        "duration": 300,
        "players": [{"account_id": 111, "isRadiant": True}, {"account_id": 222, "isRadiant": False}],
        "radiant_gold_adv": [0, 3000, 9000, 12000, 2000],
        "objectives": [{"time": 245, "type": "CHAT_MESSAGE_ROSHAN_KILL"}],
        "teamfights": [{"start": 230, "end": 260, "deaths": 4}],
    }


def test_radiant_perspective_curve_and_won():
    r = analyze(_match(), account_id=111, table=None)
    assert r["your_side"] == "radiant"
    assert r["you_won"] is True
    assert r["curve"][3]["lead"] == 12000
    assert r["curve"][3]["win_prob"] > 0.5


def test_dire_perspective_negates_lead():
    r = analyze(_match(), account_id=222, table=None)
    assert r["your_side"] == "dire"
    assert r["you_won"] is False
    assert r["curve"][3]["lead"] == -12000
    assert r["curve"][3]["win_prob"] < 0.5


def test_threw_moment_detected_and_labelled():
    r = analyze(_match(), account_id=111, table=None)
    # minute 4: big drop from a winning position -> "threw", labelled from objectives/teamfights
    m = next(x for x in r["moments"] if x["minute"] == 4)
    assert m["kind"] == "threw"
    assert m["delta"] < 0
    assert m["label"] != "big swing"  # Roshan/teamfight nearby


def test_missing_events_degrade_to_big_swing():
    match = _match()
    del match["objectives"]
    del match["teamfights"]
    r = analyze(match, account_id=111, table=None)
    m = next(x for x in r["moments"] if x["minute"] == 4)
    assert m["label"] == "big swing"


def test_no_account_id_defaults_radiant_with_note():
    r = analyze(_match(), account_id=None, table=None)
    assert r["your_side"] == "radiant"
    assert "note" in r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_review_analyze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_match'`.

- [ ] **Step 3: Implement the script**

`scripts/review_match.py`:
```python
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
```

- [ ] **Step 4: Make executable, run the analyze test**

Run:
```bash
chmod +x scripts/review_match.py
cd engine && .venv/bin/python -m pytest tests/test_review_analyze.py -v
```
Expected: PASS (5 passed). The test imports only `analyze` (pure) — no network.

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add scripts/review_match.py engine/tests/test_review_analyze.py
git commit -m "feat(scripts): OpenDota match review + pure analyze()"
```

---

### Task 3: Dashboard Review tab (Live|Review toggle + SVG win% chart)

**Files:**
- Create: `dashboard/src/panels/review.js`
- Modify: `dashboard/index.html`, `dashboard/src/main.js`, `dashboard/src/style.css`

**Interfaces:**
- Consumes: `GET /reviews` (`[{match_id, your_side, you_won, duration_s}]`); `GET /review/{id}` (the report `{your_side, you_won, curve[]{minute,win_prob,lead}, moments[]{minute,delta,win_prob,kind,label}, summary{peak_win_prob,peak_minute,threw_count}}`).
- Produces: a `Live | Review` toggle and a Review view with a match picker, an inline-SVG win% chart, a moments list, and a summary.

- [ ] **Step 1: Restructure index.html for the two views**

In `dashboard/index.html`: (a) add a nav right after the opening `<main>` tag; (b) wrap ALL the existing `<section ... class="panel">` elements in a `<div id="live-view">`; (c) add the review view after it. Concretely, the `<main>` becomes:
```html
    <main>
      <nav id="tabs">
        <button id="tab-live" class="tab active">Live</button>
        <button id="tab-review" class="tab">Review</button>
      </nav>
      <div id="live-view">
        <!-- existing panels stay here unchanged: #timings-panel, #enemies-panel, #build-panel,
             #allies-panel, #draft-panel, #macro-panel -->
      </div>
      <div id="review-view" hidden>
        <section class="panel">
          <h2>Post-game review</h2>
          <select id="review-select"><option value="">— select match —</option></select>
          <div id="review-body"><em>select a match…</em></div>
        </section>
      </div>
    </main>
```
Do not modify the existing panel sections — only wrap them in `#live-view`.

- [ ] **Step 2: Create the review panel**

`dashboard/src/panels/review.js`:
```js
function svgChart(curve, moments) {
  const W = 600, H = 160;
  if (!curve || !curve.length) return "";
  const maxMin = curve[curve.length - 1].minute || 1;
  const x = (m) => (m / maxMin) * W;
  const y = (p) => (1 - p) * H;
  const pts = curve.map((c) => `${x(c.minute).toFixed(1)},${y(c.win_prob).toFixed(1)}`).join(" ");
  const base = y(0.5).toFixed(1);
  const dots = (moments || [])
    .map((m) => `<circle cx="${x(m.minute).toFixed(1)}" cy="${y(m.win_prob).toFixed(1)}" r="4" class="mom ${m.kind}"/>`)
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="wpchart" preserveAspectRatio="none">
    <line x1="0" y1="${base}" x2="${W}" y2="${base}" class="baseline"/>
    <polyline points="${pts}" class="wpline"/>${dots}</svg>`;
}

export function renderReview(report) {
  const el = document.getElementById("review-body");
  if (!report) {
    el.innerHTML = "<em>select a match…</em>";
    return;
  }
  const s = report.summary || {};
  const moments = (report.moments || [])
    .map((m) => `<li class="mom-row ${m.kind}"><span>${Math.floor(m.minute)}:00</span>
      <b>${m.kind}</b> ${m.delta > 0 ? "+" : ""}${Math.round(m.delta * 100)}% — ${m.label}</li>`)
    .join("");
  const peak = s.peak_win_prob == null ? "—" : `${Math.round(s.peak_win_prob * 100)}%`;
  el.innerHTML = `
    <div class="rev-sum">${report.you_won ? "WON" : "LOST"} · peak ${peak} @ ${s.peak_minute}:00 · threw ${s.threw_count ?? 0}</div>
    ${svgChart(report.curve, report.moments)}
    <ul class="moments">${moments}</ul>`;
}

export function populateReviews(list) {
  const sel = document.getElementById("review-select");
  sel.innerHTML =
    `<option value="">— select match —</option>` +
    (list || []).map((r) => `<option value="${r.match_id}">${r.match_id} (${r.you_won ? "W" : "L"})</option>`).join("");
}
```

- [ ] **Step 3: Wire the toggle + fetches into main.js**

In `dashboard/src/main.js`, add the import:
```js
import { renderReview, populateReviews } from "./panels/review.js";
```
Add this block after the existing `initMacroControls(ENGINE_HOST);` call (before `connect(...)`):
```js
const base = `http://${ENGINE_HOST}`;
const liveView = document.getElementById("live-view");
const reviewView = document.getElementById("review-view");
const tabLive = document.getElementById("tab-live");
const tabReview = document.getElementById("tab-review");

function showLive() {
  liveView.hidden = false;
  reviewView.hidden = true;
  tabLive.classList.add("active");
  tabReview.classList.remove("active");
}
function showReview() {
  liveView.hidden = true;
  reviewView.hidden = false;
  tabReview.classList.add("active");
  tabLive.classList.remove("active");
  fetch(`${base}/reviews`).then((r) => r.json()).then(populateReviews).catch((e) => console.error("reviews", e));
}
tabLive.addEventListener("click", showLive);
tabReview.addEventListener("click", showReview);
document.getElementById("review-select").addEventListener("change", (e) => {
  const id = e.target.value;
  if (!id) {
    renderReview(null);
    return;
  }
  fetch(`${base}/review/${id}`).then((r) => r.json()).then(renderReview).catch((e) => console.error("review", e));
});
```

- [ ] **Step 4: Add styles**

Append to `dashboard/src/style.css`:
```css
#tabs { display: flex; gap: .4rem; margin-bottom: .6rem; }
.tab { background: #20242c; color: #b8c0cc; border: 1px solid #333; border-radius: 6px 6px 0 0; padding: .35rem .9rem; cursor: pointer; }
.tab.active { background: #11141a; color: #e6e6e6; border-bottom-color: #11141a; }
#review-select { width: 14rem; background: #0b0d11; color: #e6e6e6; border: 1px solid #20242c; border-radius: 6px; padding: .3rem; margin-bottom: .6rem; }
.rev-sum { font-weight: 600; margin-bottom: .5rem; }
.wpchart { width: 100%; height: 160px; background: #0b0d11; border: 1px solid #20242c; border-radius: 6px; }
.wpchart .baseline { stroke: #444; stroke-dasharray: 4 4; }
.wpchart .wpline { fill: none; stroke: #9ecbff; stroke-width: 2; vector-effect: non-scaling-stroke; }
.wpchart .mom.threw { fill: #ff7b7b; }
.wpchart .mom.gain { fill: #6ee787; }
.wpchart .mom.swing { fill: #ffd479; }
ul.moments { list-style: none; margin: .6rem 0 0; padding: 0; }
.mom-row { padding: .25rem 0; border-bottom: 1px solid #20242c; font-size: .85rem; }
.mom-row.threw b { color: #ff9a9a; }
.mom-row.gain b { color: #6ee787; }
.mom-row span { color: #8a93a0; font-variant-numeric: tabular-nums; margin-right: .4rem; }
```

- [ ] **Step 5: Build the dashboard**

Run: `cd dashboard && npm run build`
Expected: build succeeds, no errors. (In-browser visual smoke — switch to Review, pick a match, see the win% chart + moments — is deferred to the user, who runs `review_match.py` first to produce a report.)

- [ ] **Step 6: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add dashboard
git commit -m "feat(dashboard): post-game Review tab with SVG win% chart"
```

---

## Self-Review

- **Spec coverage:** script→cache→engine-serves architecture (Tasks 1-2, spec §3) ✓; report JSON + pure `analyze()` reusing P4a win_probability + perspective + moments + best-effort labels (Task 2, spec §4) ✓; `reviews.py` + `GET /review/{id}` + `GET /reviews` (Task 1, spec §5) ✓; dashboard Live|Review toggle + SVG chart + moments + summary (Task 3, spec §6) ✓; offline tests incl. pure analyze on a fixture + graceful missing-events (Tasks 1-2, spec §7) ✓; parsed-match requirement + parse-request path + account_id orientation (Task 2, spec §9) ✓; keyless/offline/VAC-safe engine (Global Constraints).
- **Placeholder scan:** no TBD/TODO; every code step is complete. The OpenDota field-name verification is a documented user step; `analyze()` is unit-tested on a fixture regardless.
- **Type consistency:** `REVIEWS_DIR`/`load_review`/`list_reviews` (Task 1) reused by the script's `main()` (Task 2); `analyze` (Task 2) consumes `win_probability`/`load_winprob` from P4a; the dashboard's `report.curve/moments/summary.*` field names (Task 3) match `analyze`'s output (Task 2). `main.py`'s existing routes are untouched; the two new GET routes precede the static mount.
```
