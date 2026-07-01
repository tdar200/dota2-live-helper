# Dota 2 Live Helper — P4b Post-Game Review Design Spec

**Date:** 2026-07-01
**Patch context:** 7.41d
**Status:** Design — awaiting user review before implementation planning
**Builds on:** P0-P4a (all live pillars), merged to `master`.

## 1. Goal

Add post-game review: given a match ID, fetch the fully-parsed OpenDota match (which post-game
DOES include both teams' net worth over time), reconstruct a **win-probability curve** from the
player's perspective, detect **key moments** ("where you threw / where you gained"), and render
it in a dashboard **Review tab** — a learning tool for climbing.

### Non-goals
- Not live: this analyzes a finished match, not an in-progress one.
- The engine never calls the network; only the review script does. Engine stays keyless.
- VAC-safe: post-game analysis of public match data only. No game-process access.

## 2. Decisions (from brainstorming)

- **Modality:** script → cached JSON → dashboard Review tab.
- **Reuses P4a:** the win-probability curve is `win_probability(lead, minute*60, table)` applied to
  OpenDota's per-minute net-worth advantage (empirical table if fitted, logistic fallback else).
- **Keyless offline engine / script-as-only-network-caller / graceful-degradation**, same shape
  as P3/P4a.

## 3. Architecture & data flow

```
  scripts/review_match.py <match_id> ──OpenDota /matches/{id} (parsed)──► analyze(match, account_id, table)
       (only network caller)                                                │ reuses app.winprob.win_probability
                                                                            ▼
                                                        engine/app/cache/reviews/<match_id>.json (gitignored)
                                                                            │
  Dashboard "Review" tab ─GET /review/{id}─► engine/app/reviews.py: load_review()/list_reviews() (offline)
                         ─GET /reviews──────► list of analyzed matches
```

- **`review_match.py`** fetches one match and runs the pure `analyze()`; if the match is not
  parsed (`radiant_gold_adv` absent), it triggers an OpenDota parse request (`/request/{id}`) and
  asks the user to re-run shortly.
- **`reviews.py`** (engine) reads the cached reports offline.
- **Dashboard** gains a `Live | Review` toggle in the existing single-page app.
- Engine stays keyless/offline/VAC-safe.

## 4. Report JSON + analysis

### 4.1 `engine/app/cache/reviews/<match_id>.json` (gitignored)
```json
{
  "match_id": 7654321, "generated": "...", "your_side": "radiant", "you_won": true, "duration_s": 2400,
  "curve": [ {"minute": 0, "lead": 0, "win_prob": 0.5}, {"minute": 18, "lead": 9000, "win_prob": 0.82} ],
  "moments": [ {"minute": 23, "delta": -0.24, "win_prob": 0.41, "kind": "threw", "label": "lost teamfight / Rosh"} ],
  "summary": {"peak_win_prob": 0.82, "peak_minute": 18, "threw_count": 2, "biggest_swing_min": 23}
}
```

### 4.2 `analyze(match, account_id, winprob_table) -> dict` (pure, unit-tested)
- **Robust core** needs only `radiant_gold_adv`, `radiant_win`, `players`; **event labels** are
  best-effort enrichment that degrades gracefully when `objectives`/`teamfights` are absent.
- **Perspective:** find the player whose `account_id` matches → `isRadiant` → side. `radiant_gold_adv`
  is radiant-signed; if the user is Dire, negate so `lead`/`win_prob` are the user's perspective.
  No account_id or not found → radiant perspective + a note field.
- **Curve:** per minute `i`, `lead = oriented_adv[i]`, `win_prob = win_probability(lead, i*60, table)`.
- **Moments:** consecutive-minute win% deltas with `abs(delta) >= 0.12`. `kind = "threw"` when
  `delta < 0` and the prior win% > 0.6 (ahead, then dropped); `kind = "gain"` when `delta > 0`;
  else `"swing"`. Each labeled best-effort from `objectives`/`teamfights` near that minute
  (tower/Rosh/aegis; teamfight net gold + deaths); if nothing found → `"big swing"`.
- **Summary:** `peak_win_prob`/`peak_minute`, `threw_count`, `biggest_swing_min`.

### 4.3 Honest caveat
Exact OpenDota `objectives`/`teamfights` field names are verified against a real parsed match; the
pure `analyze()` is tested on a fixture, and the curve + swings work regardless of the enrichment
fields (which only affect moment *labels*).

## 5. Engine — serving reports (`reviews.py`)

- `load_review(match_id: int, dir=REVIEWS_DIR) -> dict | None` — reads `<dir>/<match_id>.json` or None.
- `list_reviews(dir=REVIEWS_DIR) -> list[dict]` — one entry per cached report:
  `{match_id, your_side, you_won, duration_s}` (summary metadata; empty list when the dir is absent).
- `main.py`: `GET /review/{match_id}` (404 when absent, the report JSON when present);
  `GET /reviews` (the list). Routes added before the static mount.

## 6. Dashboard Review tab

- A top **`Live | Review`** toggle (show/hide sections; no second Vite build entry).
- **Review view:** a match picker populated from `GET /reviews`; selecting one fetches
  `GET /review/{id}` and renders:
  - An **inline-SVG win% line chart** (0–100% over minutes, a 50% baseline, dots at key moments) —
    vanilla, no chart library; the SVG path is computed from `curve`.
  - A **moments list** (minute · win% delta · kind badge · label); "threw" red, "gain" green.
  - A **summary** line (result, peak win% & minute, threw count).

## 7. Testing

- **`analyze()` tests** (pure, synthetic match fixture): perspective orientation (Dire negates),
  win% via table/fallback, swing detection + "threw" classification, graceful when
  `objectives`/`teamfights` absent.
- **`reviews.py` tests:** `load_review` missing → None; `list_reviews` empty dir → [].
- **Endpoint tests:** `GET /review/{id}` 404 absent / JSON present; `GET /reviews` lists.
- No live network in any test; the OpenDota fetch wrapper is not unit-tested.

## 8. Internal build order

1. `reviews.py` loader + `GET /review/{match_id}` + `GET /reviews` + tests (serve a hand-placed
   fixture report — no analysis dependency).
2. `scripts/review_match.py`: OpenDota fetch (timeout + error handling) + pure `analyze()` + a
   transform test on a synthetic match; parse-request-if-unparsed path.
3. Dashboard Review tab + SVG win% chart + moments list.

## 9. Honest notes / open items

- The match must be **parsed** on OpenDota; the script triggers a parse request if not and asks the
  user to re-run shortly (parsing takes a minute or two).
- `account_id` orients "you" (env `DOTA_ACCOUNT_ID` or `--account-id`); absent → radiant perspective.
- Event labels are best-effort; the win% curve and swing detection are the reliable core.
- Reports load from the gitignored cache; the engine serves whatever `review_match.py` has written.
