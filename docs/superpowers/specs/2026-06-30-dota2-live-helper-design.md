# Dota 2 Live Helper — Design Spec

**Date:** 2026-06-30
**Patch context:** 7.41d
**Status:** Design — awaiting user review before implementation planning

## 1. Goal

A complete, personal "Dota Plus–like" in-game assistant whose purpose is to **win more
games and climb out of Herald**. It uses the user's own data and calculations (no
subscription, no Valve ML), runs alongside live Dota 2 matches, and surfaces actionable
advice on a second-monitor web dashboard.

It is the **live half** layered on top of the user's existing
[`dota2-knowledge-base`](../../../../dota2-knowledge-base) (the static half: patch-7.41d
game data, formulas, and build guides).

### Non-goals
- Not a cheat. Uses only Valve's official Game State Integration (GSI), public APIs
  (OpenDota / Stratz), and the user's own manual inputs. **No memory reads, no injection,
  nothing the player could not legitimately see.** 100% VAC-safe.
- Not a generic public product. Single-user, local, tuned to the user's account and bracket.

## 2. Environment & constraints

- **OS:** Linux (Ubuntu 24.04, GNOME) on **X11**, native Steam.
- **Displays:** 2 monitors (laptop eDP + HDMI external) → second-screen dashboard is trivial.
- **Stack:** Python engine (FastAPI) + JS frontend dashboard.
- Overwolf and most overlay tools are Windows-only and are **not** used. An X11 transparent
  overlay is a possible *later* front-end (see §8), but v1 is a second-screen web dashboard.

## 3. Approach

A **single FastAPI process** that:
1. receives GSI POSTs at `/gsi`,
2. runs the engine (feature modules over a shared in-memory `GameState`),
3. serves the built JS dashboard,
4. pushes a combined advice payload to the dashboard over WebSocket.

During development the JS dev server runs separately; for real use it is **one command,
one process**. This preserves the clean Python-engine / JS-frontend split while keeping
exactly one thing to run mid-match.

## 4. Architecture & data flow

```
                        ┌─────────────────────────────────────────┐
   Dota 2 client        │            FastAPI engine (Python)        │
   (GSI config file) ──POST──►  /gsi  ── ingest ─► GameState (in-mem)│
                        │                              │            │
                        │   ┌──────────────────────────▼─────────┐  │
                        │   │  Feature modules (read GameState)   │  │
                        │   │   • timings   • build coach         │  │
                        │   │   • draft     • win-prob / macro     │  │
                        │   └──────────────┬──────────────────────┘  │
   Knowledge base ──────►  static loader   │ Advice objects          │
   OpenDota / Stratz ──►  data layer ──► WebSocket push ──┐          │
   (cached, between games)               (combined payload)│         │
                        └──────────────────────────────────┼─────────┘
                                                            ▼
                                          JS dashboard (2nd monitor) — live panels
```

**Two deliberately separated data clocks:**
- **Live (per-tick, from GSI):** the player's hero/items/abilities/gold, the game clock,
  day/night, buyback. Drives timings and current-state advice.
- **Cold (cached, refreshed between games):** the KB + OpenDota/Stratz aggregates (matchup
  win rates, item win rates, the user's pocket-hero stats and match history). A live match
  never blocks on a network call.

**Core principle — the engine is display-agnostic.** It emits advice objects; today a web
page renders them, later an X11 overlay can subscribe to the same WebSocket unchanged.

## 5. Engine modules

One shared read-only `GameState` feeds four modules; each emits advice objects.

- **Timings** — pure math on the GSI game clock. Bounty / water / power / wisdom runes,
  neutral-item tiers, day↔night, the `:53` stack window, tome, buyback-ready (from GSI
  `buyback_cost` / `buyback_cooldown`). Emits upcoming events + countdowns.
- **Build coach** — reads the player's hero, current items, gold. Looks up the KB build for
  the hero, cross-checks OpenDota item win-rates for the bracket, and (when enemy heroes are
  known) tilts toward situational items. Emits "buy next / skill next."
- **Draft helper** — fires at hero-select. Given enemy + ally picks, ranks counters, synergy,
  and the user's pocket heroes by personal + Herald win rate. Emits a ranked pick list with
  one-line reasons.
- **Win-prob / macro** — a live read from observable signals (team net-worth-lead proxy, key
  timings, buyback states) plus a "what to do now" nudge (push / farm / defend / smoke). The
  *learning* half runs **post-game** on OpenDota's fully-parsed match to refine the model.

## 6. Data sources & honest GSI limits

GSI in **player mode** reliably gives the player's own hero/items/abilities/gold, the clock,
day/night, and buyback. It does **not** reliably expose enemy draft picks, enemy net worth,
or Roshan state. The design builds in honest fallbacks rather than pretending:

| Need | Reliable source | Fallback |
|---|---|---|
| Clock-based timings | GSI clock (exact) | none needed |
| Player build progress | GSI items/gold | none needed |
| Enemy heroes (draft & build coach) | partial via GSI | **dashboard quick-entry** — click enemy portraits once; persists for the match |
| Roshan timer | not in GSI | **"Rosh died" button** → starts the 8–11 min window |
| Enemy net worth (win-prob) | not live | live meter uses observable proxies; **full fidelity from the post-game parsed match** |

**Cold data sources** (cached locally, refreshed between games):
- The existing `dota2-knowledge-base` (builds, formulas, raw dotaconstants JSON).
- OpenDota API (free, no key): `heroStats` (bracket win rates), matchups, item win rates,
  the user's `players/{id}/matches`.
- Stratz (GraphQL, free key) for richer matchup/role data and parsed match detail.
- Ground-truth values, if ever needed, from the local Dota VPK files.

The user supplies their **Steam / OpenDota account ID** once (config) for personalization.

## 7. Dashboard

One page, four panels, live over WebSocket, sized for the second monitor:
- **Timings ticker** — next events + countdowns.
- **Build coach** — next item / skill, with reasons.
- **Draft** — auto-shown at hero select; ranked pick list.
- **Win-prob / macro** — meter + "what to do now."
- A small **enemy-portrait quick-entry bar** feeds draft + build coach. A **"Rosh died"**
  button feeds the timings panel.

## 8. Build order (all four pillars stay in scope; this is sequencing only)

- **P0 — Backbone:** `/gsi` listener + `GameState` + WebSocket + dashboard shell + GSI config
  installed. Exit criterion: live data confirmed flowing in a real match.
- **P1 — Timings:** pure clock; instant value, validates the loop end-to-end.
- **P2 — Build coach:** wire KB + OpenDota cache + enemy quick-entry.
- **P3 — Draft helper:** hero-select panel; shares enemy quick-entry.
- **P4 — Win-prob / macro:** live proxy meter + post-game parsed-match learning.

Each phase ends with a working, usable tool — no phase is throwaway.

## 9. Testing

- **GSI replay fixtures:** record real GSI POST streams to JSON files; replay them into the
  engine for deterministic tests of every module — no need to be in a live game.
- Unit tests for clock math (timings) and KB/data lookups.
- Manual in-match smoke test at the end of each phase.

## 10. GSI setup

A config file is installed to:
`~/.local/share/Steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/gamestate_integration_helper.cfg`
pointing at the local engine endpoint, with the data blocks the modules need and an update
rate suitable for live advice.

## 11. Open items to resolve during planning

- Exact JS dashboard framework (Vite + lightweight framework vs vanilla).
- Precise current-patch rune/stack/neutral timing constants (verify against KB + in-client).
- Win-prob proxy formula for the live meter (observable signals only).
