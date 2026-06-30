"""Patch 7.41d periodic-event timings, in seconds of game clock_time.

Cross-checked against ../dota2-knowledge-base. Correct here if the client disagrees;
the timing math (modules/timings.py) is patch-agnostic and tested separately.

KB note: dota2-knowledge-base/game-data-and-formulas.md, PATCH-7.41-reworks-reference.md
and README.md contain no rune/lotus/neutral/cycle timing data. ALL constants below retain
the brief's documented 7.41d defaults; they are marked "KB silent" in the comments.
Verify in-client if exact timings matter (especially Neutral T5 and stack window start).
"""
from app.modules.timings import PeriodicEvent

GAME_EVENTS: list[PeriodicEvent] = [
    # Bounty runes: at 0:00, then every 3:00. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Bounty runes", first_spawn_s=0, interval_s=180, category="rune"),
    # Water runes: 2:00 and 4:00 only. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Water rune", first_spawn_s=120, interval_s=120, end_s=240, category="rune"),
    # Power runes: every 2:00 from 6:00. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Power rune", first_spawn_s=360, interval_s=120, category="rune"),
    # Wisdom runes: 7:00, then every 7:00. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Wisdom rune", first_spawn_s=420, interval_s=420, category="rune"),
    # Lotus pool: every 3:00 from 3:00. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Lotus", first_spawn_s=180, interval_s=180, category="lotus"),
    # Neutral item tiers (one-shot unlocks). (KB silent — kept 7.41d defaults)
    PeriodicEvent(name="Neutral T1", first_spawn_s=420, interval_s=None, category="neutral"),   # 7:00
    PeriodicEvent(name="Neutral T2", first_spawn_s=1020, interval_s=None, category="neutral"),  # 17:00
    PeriodicEvent(name="Neutral T3", first_spawn_s=1620, interval_s=None, category="neutral"),  # 27:00
    PeriodicEvent(name="Neutral T4", first_spawn_s=2220, interval_s=None, category="neutral"),  # 37:00
    PeriodicEvent(name="Neutral T5", first_spawn_s=3600, interval_s=None, category="neutral"),  # 60:00
    # Day/night flips every 5:00; first night at 5:00. (KB silent — kept 7.41d default)
    PeriodicEvent(name="Night/Day flip", first_spawn_s=300, interval_s=300, category="cycle"),
    # Camp stack window (pull at x:53 every minute, from 1:53). (KB silent — kept 7.41d default)
    PeriodicEvent(name="Stack camp", first_spawn_s=113, interval_s=60, category="stack"),
]
