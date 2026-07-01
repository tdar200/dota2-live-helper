"""Tests for the PURE transform functions in scripts/refresh_hero_meta.py.

No network. Adds scripts/ to sys.path (mirrors test_refresh_item_builds_transform.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from refresh_hero_meta import (  # noqa: E402
    HERALD_BRACKET,
    bracket_winrate,
    transform_hero_meta_row,
    transform_hero_stats,
)

# A trimmed real-shaped heroStats row (Anti-Mage, live values 2026-07-01).
AM_ROW = {
    "id": 1,
    "name": "npc_dota_hero_antimage",
    "localized_name": "Anti-Mage",
    "1_pick": 31796, "1_win": 16151,   # Herald
    "2_pick": 79424, "2_win": 39977,
    "8_pick": 0,     "8_win": 0,       # Immortal — no pub picks
}

ID_TO_KEY = {1: "npc_dota_hero_antimage", 2: "npc_dota_hero_axe"}


# ---------------------------------------------------------------------------
# bracket_winrate
# ---------------------------------------------------------------------------

def test_bracket_winrate_herald():
    assert bracket_winrate(AM_ROW, HERALD_BRACKET) == round(16151 / 31796, 4)


def test_herald_is_bracket_one():
    assert HERALD_BRACKET == 1


def test_bracket_winrate_default_is_herald():
    assert bracket_winrate(AM_ROW) == bracket_winrate(AM_ROW, 1)


def test_bracket_winrate_zero_picks_returns_none():
    # Immortal (bracket 8) has 0 picks -> None, never ZeroDivisionError
    assert bracket_winrate(AM_ROW, 8) is None


def test_bracket_winrate_missing_keys_returns_none():
    assert bracket_winrate({}, HERALD_BRACKET) is None


def test_bracket_winrate_in_unit_range():
    wr = bracket_winrate(AM_ROW, HERALD_BRACKET)
    assert 0.0 <= wr <= 1.0


# ---------------------------------------------------------------------------
# transform_hero_meta_row
# ---------------------------------------------------------------------------

def test_transform_row_shape():
    entry = transform_hero_meta_row(AM_ROW)
    assert entry == {
        "herald_winrate": round(16151 / 31796, 4),
        "herald_pick": 31796,
        "herald_win": 16151,
    }


def test_transform_row_missing_id_dropped():
    assert transform_hero_meta_row({"1_pick": 10, "1_win": 5}) is None


def test_transform_row_zero_picks_winrate_none_but_kept():
    entry = transform_hero_meta_row({"id": 9, "1_pick": 0, "1_win": 0})
    assert entry is not None
    assert entry["herald_winrate"] is None
    assert entry["herald_pick"] == 0


# ---------------------------------------------------------------------------
# transform_hero_stats
# ---------------------------------------------------------------------------

def test_transform_stats_keys_by_hero_key():
    out = transform_hero_stats([AM_ROW], ID_TO_KEY)
    assert set(out) == {"npc_dota_hero_antimage"}
    assert out["npc_dota_hero_antimage"]["herald_pick"] == 31796


def test_transform_stats_skips_unknown_id():
    stray = {"id": 9999, "1_pick": 10, "1_win": 5}
    out = transform_hero_stats([AM_ROW, stray], ID_TO_KEY)
    assert "npc_dota_hero_antimage" in out
    assert len(out) == 1  # stray id not in heroes.json -> dropped


def test_transform_stats_empty_input():
    assert transform_hero_stats([], ID_TO_KEY) == {}
