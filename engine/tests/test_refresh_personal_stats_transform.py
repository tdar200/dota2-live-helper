"""Unit tests for scripts/refresh_personal_stats.py pure transforms (NO network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh_personal_stats as rp  # noqa: E402


# --- won_from_slot ---------------------------------------------------------

def test_won_radiant_slot_radiant_win():
    assert rp.won_from_slot(0, True) is True
    assert rp.won_from_slot(4, True) is True


def test_won_radiant_slot_dire_win():
    assert rp.won_from_slot(2, False) is False


def test_won_dire_slot_dire_win():
    assert rp.won_from_slot(128, False) is True
    assert rp.won_from_slot(132, False) is True


def test_won_dire_slot_radiant_win():
    assert rp.won_from_slot(130, True) is False


# --- transform_player_heroes ----------------------------------------------

def test_transform_player_heroes_basic():
    rows = [
        {"hero_id": 20, "games": 40, "win": 24, "last_played": 111},
        {"hero_id": 1, "games": 10, "win": 3, "last_played": 222},
    ]
    id_to_key = {20: "npc_dota_hero_silencer", 1: "npc_dota_hero_antimage"}
    out = rp.transform_player_heroes(rows, id_to_key)
    assert out["npc_dota_hero_silencer"] == {
        "games": 40, "wins": 24, "winrate": 0.6, "last_played": 111,
    }
    assert out["npc_dota_hero_antimage"]["winrate"] == 0.3


def test_transform_player_heroes_skips_zero_games_and_unknown_id():
    rows = [
        {"hero_id": 20, "games": 0, "win": 0},        # zero games -> skip
        {"hero_id": 999, "games": 5, "win": 2},       # unknown id -> skip
        {"games": 5, "win": 2},                       # no hero_id -> skip
    ]
    out = rp.transform_player_heroes(rows, {20: "npc_dota_hero_silencer"})
    assert out == {}


# --- find_player -----------------------------------------------------------

def test_find_player_by_slot():
    match = {"players": [
        {"player_slot": 0, "hero_id": 5},
        {"player_slot": 132, "hero_id": 20},
    ]}
    assert rp.find_player(match, 132)["hero_id"] == 20


def test_find_player_falls_back_to_hero_id():
    match = {"players": [{"player_slot": 1, "hero_id": 20}]}
    # slot 5 absent -> fall back to hero_id 20
    assert rp.find_player(match, 5, hero_id=20)["player_slot"] == 1


def test_find_player_missing_returns_none():
    match = {"players": [{"player_slot": 0, "hero_id": 5}]}
    assert rp.find_player(match, 99, hero_id=77) is None


def test_find_player_refuses_ambiguous_mirror_hero():
    # Same hero on both teams; slot absent -> refuse to guess (could be enemy).
    match = {"players": [
        {"player_slot": 1, "hero_id": 20},    # us? enemy? can't tell
        {"player_slot": 129, "hero_id": 20},  # mirror on the other side
    ]}
    assert rp.find_player(match, 5, hero_id=20) is None


# --- extract_item_keys -----------------------------------------------------

ITEM_IDS = {
    "1": "blink",
    "2": "manta",
    "3": "tpscroll",     # blocklisted
    "4": "tango",        # blocklisted
    "5": "power_treads",
    "6": "clarity",      # qual consumable
    "999": "recipe_x",   # dname None
}
ITEMS = {
    "blink":       {"dname": "Blink Dagger", "qual": "component"},
    "manta":       {"dname": "Manta Style", "qual": "epic"},
    "tpscroll":    {"dname": "Town Portal Scroll", "qual": "consumable"},
    "tango":       {"dname": "Tango", "qual": "consumable"},
    "power_treads": {"dname": "Power Treads", "qual": "common"},
    "clarity":     {"dname": "Clarity", "qual": "consumable"},
    "recipe_x":    {"dname": None},
}


def test_extract_item_keys_filters_and_dedups():
    player = {
        "item_0": 2,      # manta
        "item_1": 1,      # blink
        "item_2": 3,      # tpscroll -> drop (blocklist)
        "item_3": 4,      # tango -> drop (blocklist)
        "item_4": 5,      # power_treads
        "item_5": 0,      # empty
        "item_neutral": 2,  # manta again -> dedup
    }
    keys = rp.extract_item_keys(player, ITEM_IDS, ITEMS)
    assert keys == ["item_manta", "item_blink", "item_power_treads"]


def test_extract_item_keys_drops_unknown_and_recipe_and_consumable_qual():
    player = {"item_0": 777, "item_1": 999, "item_2": 6}  # unknown, recipe, clarity(qual)
    assert rp.extract_item_keys(player, ITEM_IDS, ITEMS) == []


# --- aggregation + payload -------------------------------------------------

def test_add_and_finalize_item_agg_winrate():
    agg: dict = {}
    rp.add_match_items(agg, "npc_dota_hero_silencer", ["item_manta", "item_blink"], won=True)
    rp.add_match_items(agg, "npc_dota_hero_silencer", ["item_manta"], won=False)
    final = rp.finalize_item_agg(agg)
    s = final["npc_dota_hero_silencer"]
    assert s["item_manta"] == {"games": 2, "wins": 1, "winrate": 0.5}
    assert s["item_blink"] == {"games": 1, "wins": 1, "winrate": 1.0}


def test_finalize_respects_min_games():
    agg = {"h": {"item_a": {"games": 1, "wins": 1}, "item_b": {"games": 3, "wins": 2}}}
    final = rp.finalize_item_agg(agg, min_games=2)
    assert "item_a" not in final["h"]
    assert final["h"]["item_b"]["games"] == 3


def test_build_match_history_derives_win_and_sorts_newest_first():
    id_to_key = {8: "npc_dota_hero_juggernaut", 35: "npc_dota_hero_sniper"}
    matches = [
        {"match_id": 100, "start_time": 1000, "player_slot": 2, "radiant_win": True,
         "hero_id": 8, "kills": 5, "deaths": 2, "assists": 7, "duration": 2100,
         "party_size": 1, "average_rank": 14},
        {"match_id": 200, "start_time": 3000, "player_slot": 130, "radiant_win": True,
         "hero_id": 35},  # Dire slot, radiant won -> loss
        {"match_id": 300, "start_time": 2000, "player_slot": 0, "radiant_win": None,
         "hero_id": 8},   # undecided -> win None
    ]
    out = rp.build_match_history(matches, id_to_key)
    assert [r["match_id"] for r in out] == [200, 300, 100]  # newest start_time first
    m100 = next(r for r in out if r["match_id"] == 100)
    assert m100["win"] is True and m100["hero"] == "npc_dota_hero_juggernaut"
    assert m100["kills"] == 5
    m200 = next(r for r in out if r["match_id"] == 200)
    assert m200["win"] is False   # dire slot, radiant win
    m300 = next(r for r in out if r["match_id"] == 300)
    assert m300["win"] is None    # radiant_win missing


def test_build_payload_carries_match_history():
    payload = rp.build_payload(
        1, {}, {}, set(), "2026-07-01T00:00:00Z",
        match_history=[{"match_id": 7, "win": True}],
    )
    assert payload["match_history"] == [{"match_id": 7, "win": True}]
    # default is an empty list, never missing
    p2 = rp.build_payload(1, {}, {}, set(), "2026-07-01T00:00:00Z")
    assert p2["match_history"] == []


def test_build_payload_and_roundtrip_resume():
    agg: dict = {}
    rp.add_match_items(agg, "h", ["item_manta"], won=True)
    payload = rp.build_payload(
        123, {"h": {"games": 1, "wins": 1, "winrate": 1.0, "last_played": 9}},
        agg, {5, 5, 7}, "2026-07-01T00:00:00Z",
    )
    assert payload["account_id"] == 123
    assert payload["processed_match_ids"] == [5, 7]
    assert payload["items"]["h"]["item_manta"]["winrate"] == 1.0
    # resume: rebuild the games/wins aggregate from the saved payload
    reloaded = rp.item_agg_from_payload(payload)
    assert reloaded["h"]["item_manta"] == {"games": 1, "wins": 1}
