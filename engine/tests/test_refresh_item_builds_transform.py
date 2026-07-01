"""Tests for the PURE transform functions in scripts/refresh_item_builds.py.

No network. Adds scripts/ to sys.path (mirrors test_refresh_transform.py pattern).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from refresh_item_builds import (
    CONSUMABLE_BLOCKLIST,
    PHASE_MAP,
    resolve_item,
    transform_item_popularity,
    transform_benchmarks,
    build_hero_entry,
)

# ---------------------------------------------------------------------------
# Minimal constant stubs shared across tests
# ---------------------------------------------------------------------------

# item_ids: numeric_id (str) -> short_name
ITEM_IDS = {
    "152": "bfury",           # Battle Fury — finished item
    "63":  "power_treads",    # Power Treads — finished item
    "116": "manta",           # Manta Style — finished item
    "44":  "quelling_blade",  # Quelling Blade — finished item (start)
    "999": "recipe_bfury",    # recipe — dname is None
    "10":  "yasha",           # component — qual=="component"
    "20":  "tango",           # consumable in blocklist
    "30":  "blink",           # Blink Dagger — finished item
}

# items: short_name -> metadata
ITEMS = {
    "bfury":         {"dname": "Battle Fury",     "qual": "artifact"},
    "power_treads":  {"dname": "Power Treads",    "qual": "common"},
    "manta":         {"dname": "Manta Style",     "qual": "artifact"},
    "quelling_blade":{"dname": "Quelling Blade",  "qual": "common"},
    "recipe_bfury":  {"dname": None,              "qual": "common"},   # null dname → skip
    "yasha":         {"dname": "Yasha",           "qual": "component"},# component → skip
    "tango":         {"dname": "Tango",           "qual": "consumable"},# consumable → skip
    "blink":         {"dname": "Blink Dagger",    "qual": "artifact"},
}


# ===========================================================================
# PHASE_MAP
# ===========================================================================

def test_phase_map_contains_all_four_keys():
    assert "start_game_items"  in PHASE_MAP
    assert "early_game_items"  in PHASE_MAP
    assert "mid_game_items"    in PHASE_MAP
    assert "late_game_items"   in PHASE_MAP


def test_phase_map_values():
    assert PHASE_MAP["start_game_items"]  == "start_game"
    assert PHASE_MAP["early_game_items"]  == "early_game"
    assert PHASE_MAP["mid_game_items"]    == "mid_game"
    assert PHASE_MAP["late_game_items"]   == "late_game"


# ===========================================================================
# CONSUMABLE_BLOCKLIST
# ===========================================================================

def test_blocklist_contains_required_entries():
    required = {
        "ward_observer", "ward_sentry", "tpscroll", "dust",
        "smoke_of_deceit", "tango", "clarity", "flask",
        "enchanted_mango", "faerie_fire", "branches",
    }
    assert required.issubset(CONSUMABLE_BLOCKLIST)


# ===========================================================================
# resolve_item
# ===========================================================================

def test_resolve_item_returns_correct_dict():
    result = resolve_item(152, ITEM_IDS, ITEMS)
    assert result is not None
    assert result["id"] == 152
    assert result["key"] == "item_bfury"
    assert result["display"] == "Battle Fury"


def test_resolve_item_key_has_item_prefix():
    result = resolve_item(30, ITEM_IDS, ITEMS)
    assert result is not None
    assert result["key"] == "item_blink"


def test_resolve_item_null_dname_returns_none():
    """Recipes / tokens have dname: null — must be dropped."""
    result = resolve_item(999, ITEM_IDS, ITEMS)
    assert result is None


def test_resolve_item_component_returns_none():
    """qual=='component' items (e.g. Yasha) must be dropped."""
    result = resolve_item(10, ITEM_IDS, ITEMS)
    assert result is None


def test_resolve_item_consumable_qual_returns_none():
    """qual=='consumable' items must be dropped."""
    result = resolve_item(20, ITEM_IDS, ITEMS)
    assert result is None


def test_resolve_item_blocklist_name_returns_none():
    """Names in CONSUMABLE_BLOCKLIST must be dropped even if qual is fine."""
    # Build a fake items dict where tango has a non-consumable qual
    # to verify the blocklist check is separate from the qual check
    item_ids_fake = {"20": "tango"}
    items_fake    = {"tango": {"dname": "Tango", "qual": "artifact"}}
    result = resolve_item(20, item_ids_fake, items_fake)
    assert result is None


def test_resolve_item_unknown_id_returns_none():
    """Id not present in item_ids → None."""
    result = resolve_item(9999, ITEM_IDS, ITEMS)
    assert result is None


def test_resolve_item_unknown_name_returns_none():
    """Id maps to a name not present in items → None."""
    item_ids_partial = {"1": "unknown_item"}
    result = resolve_item(1, item_ids_partial, ITEMS)
    assert result is None


# ===========================================================================
# transform_item_popularity — phase-key translation
# ===========================================================================

def test_phase_key_translated_from_opendota_suffix():
    """OpenDota key 'mid_game_items' → output key 'mid_game'."""
    pop = {"mid_game_items": {"152": 30}}
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)
    assert "mid_game" in out
    assert "mid_game_items" not in out


def test_all_four_phases_present_in_output():
    pop = {
        "start_game_items": {"44": 100},
        "early_game_items": {"63": 80},
        "mid_game_items":   {"152": 60},
        "late_game_items":  {"116": 40},
    }
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)
    assert set(out.keys()) == {"start_game", "early_game", "mid_game", "late_game"}


# ===========================================================================
# transform_item_popularity — null-dname skip
# ===========================================================================

def test_null_dname_item_absent_from_output():
    pop = {"mid_game_items": {"999": 50, "152": 30}}  # 999=recipe (dname=None)
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)
    keys = [it["key"] for it in out.get("mid_game", [])]
    assert "item_recipe_bfury" not in keys
    assert "item_bfury" in keys


# ===========================================================================
# transform_item_popularity — component + consumable filter
# ===========================================================================

def test_component_item_dropped():
    """Yasha (qual==component) must not appear."""
    pop = {"mid_game_items": {"10": 200, "152": 100}}
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)
    keys = [it["key"] for it in out.get("mid_game", [])]
    assert "item_yasha" not in keys


def test_consumable_item_dropped():
    """Tango must not appear."""
    pop = {"start_game_items": {"20": 9999, "44": 100}}
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)
    keys = [it["key"] for it in out.get("start_game", [])]
    assert "item_tango" not in keys
    assert "item_quelling_blade" in keys


# ===========================================================================
# transform_item_popularity — cross-phase dedup
# ===========================================================================

def test_cross_phase_dedup_keeps_earliest():
    """power_treads present in early, mid, late → appears only in early_game."""
    pop = {
        "start_game_items": {"44": 100},          # quelling_blade
        "early_game_items": {"63": 80},            # power_treads
        "mid_game_items":   {"63": 70, "152": 60}, # power_treads again + bfury
        "late_game_items":  {"63": 50, "116": 40}, # power_treads again + manta
    }
    out = transform_item_popularity(pop, ITEM_IDS, ITEMS)

    early_keys = [it["key"] for it in out.get("early_game", [])]
    mid_keys   = [it["key"] for it in out.get("mid_game",   [])]
    late_keys  = [it["key"] for it in out.get("late_game",  [])]

    assert "item_power_treads" in early_keys
    assert "item_power_treads" not in mid_keys
    assert "item_power_treads" not in late_keys


# ===========================================================================
# transform_item_popularity — cap (top_n) and sort order
# ===========================================================================

def _make_many_items(n: int):
    """Build item_ids + items dicts for n unique finished items."""
    item_ids = {}
    items    = {}
    for i in range(n):
        key = f"item_{i}"
        item_ids[str(i)] = key
        items[key] = {"dname": f"Item {i}", "qual": "artifact"}
    return item_ids, items


def test_cap_at_top_n():
    """12 items in a phase → exactly 8 (default top_n)."""
    item_ids, items = _make_many_items(12)
    # counts are 12,11,10,...,1
    pop = {"mid_game_items": {str(i): 12 - i for i in range(12)}}
    out = transform_item_popularity(pop, item_ids, items)
    assert len(out.get("mid_game", [])) == 8


def test_sorted_desc_by_count():
    """Items within a phase are sorted descending by count."""
    item_ids = {"152": "bfury", "116": "manta", "63": "power_treads"}
    items_local = {
        "bfury":        {"dname": "Battle Fury",  "qual": "artifact"},
        "manta":        {"dname": "Manta Style",  "qual": "artifact"},
        "power_treads": {"dname": "Power Treads", "qual": "common"},
    }
    pop = {"mid_game_items": {"116": 500, "152": 300, "63": 100}}
    out = transform_item_popularity(pop, item_ids, items_local)
    counts = [it["count"] for it in out["mid_game"]]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == 500


# ===========================================================================
# transform_benchmarks
# ===========================================================================

BENCH_RESULT = {
    "gold_per_min":      [{"percentile": p/10, "value": v}
                          for p, v in zip(range(1, 12),
                                          [312,378,431,479,527,578,634,701,792,861,988])],
    "xp_per_min":        [{"percentile": p/10, "value": v}
                          for p, v in zip(range(1, 12),
                                          [402,468,521,569,617,668,724,791,882,951,1078])],
    "last_hits_per_min": [{"percentile": p/10, "value": v}
                          for p, v in zip(range(1, 12),
                                          [3.1,4.0,4.7,5.3,5.9,6.5,7.2,8.0,9.1,9.9,11.4])],
    "hero_damage_per_min": [{"percentile": 0.1, "value": 100}],  # must be dropped
}


def test_transform_benchmarks_returns_four_keys():
    out = transform_benchmarks(BENCH_RESULT)
    assert set(out.keys()) == {"percentiles", "gold_per_min", "xp_per_min", "last_hits_per_min"}


def test_transform_benchmarks_drops_hero_damage():
    out = transform_benchmarks(BENCH_RESULT)
    assert "hero_damage_per_min" not in out


def test_transform_benchmarks_length_11():
    out = transform_benchmarks(BENCH_RESULT)
    assert len(out["percentiles"])       == 11
    assert len(out["gold_per_min"])      == 11
    assert len(out["xp_per_min"])        == 11
    assert len(out["last_hits_per_min"]) == 11


def test_transform_benchmarks_arrays_ascending():
    out = transform_benchmarks(BENCH_RESULT)
    for key in ("percentiles", "gold_per_min", "xp_per_min", "last_hits_per_min"):
        arr = out[key]
        assert arr == sorted(arr), f"{key} not ascending"


def test_transform_benchmarks_correct_values():
    out = transform_benchmarks(BENCH_RESULT)
    assert out["gold_per_min"][0]  == 312
    assert out["gold_per_min"][-1] == 988
    assert abs(out["last_hits_per_min"][0] - 3.1) < 1e-9


# ===========================================================================
# build_hero_entry integration
# ===========================================================================

def test_build_hero_entry_shape():
    """build_hero_entry assembles the full per-hero dict correctly."""
    hero    = "npc_dota_hero_juggernaut"
    item_pop = {
        "start_game_items": {"44": 100},
        "early_game_items": {"63": 80},
        "mid_game_items":   {"152": 60},
        "late_game_items":  {"116": 40},
    }
    entry = build_hero_entry(hero, item_pop, BENCH_RESULT, ITEM_IDS, ITEMS)
    assert entry["hero_id"] is None or isinstance(entry["hero_id"], int)
    assert "builds" in entry
    assert "benchmarks" in entry
    assert entry["display"] == "Juggernaut" or isinstance(entry["display"], str)
    assert "early_game" in entry["builds"]
    assert "percentiles" in entry["benchmarks"]


def test_build_hero_entry_no_timestamp():
    """build_hero_entry must NOT include a timestamp (timestamp goes in main)."""
    entry = build_hero_entry(
        "npc_dota_hero_juggernaut",
        {"start_game_items": {"44": 10}},
        BENCH_RESULT,
        ITEM_IDS,
        ITEMS,
    )
    assert "generated_at" not in entry
    assert "timestamp"    not in entry
