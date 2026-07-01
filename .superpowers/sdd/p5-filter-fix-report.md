# P5 Item-Build Filter Fix Report

**Status:** DONE

**py_compile:** `python3 -m py_compile scripts/refresh_item_builds.py` → OK

**Tests:** `cd engine && .venv/bin/python -m pytest tests/test_refresh_item_builds_transform.py -v` → 32 passed (was 27; +5 new assertions). Full suite: `pytest tests -q` → 114 passed.

**New rule (structural, not qual-based):** An item is dropped iff it is ATOMIC (`components` absent/None) AND it appears in at least one other item's `components` list (`part_keys`). This keeps Blink Dagger (atomic but used as nobody's part), all assembled items (have components), and atomic finished items like Quelling Blade; drops raw stat sticks (Mystic Staff, Orb of Frost, etc.) that are atomic AND referenced by assembled items.

**Key changes:**
- `component_part_keys(items)` helper added — O(n) scan, pure.
- `resolve_item` takes new `part_keys: set[str]` param; drops qual=="component" → structural check; keeps qual=="consumable" drop.
- `transform_item_popularity` computes `part_keys` once, passes to every `resolve_item` call.
- Tests: rewrote `test_resolve_item_component_returns_none` → structural rule; added blink regression guard, assembled-also-a-part kept, `component_part_keys` unit tests; updated ITEMS fixture with `components` fields.
