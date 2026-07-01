from app.build_data import load_build_data, TRAITS


def test_load_build_data_parses_and_validates():
    data = load_build_data()
    # core climbers present
    assert "npc_dota_hero_skeleton_king" in data.builds
    assert data.builds["npc_dota_hero_skeleton_king"].display == "Wraith King"
    assert len(data.builds) >= 11

    # every build's items have display names; every situational trait is valid
    for hero, build in data.builds.items():
        for item in build.core_items + build.starting_items:
            assert item in data.item_names, f"{hero}: no name for {item}"
        for s in build.situational:
            assert s.trait in TRAITS, f"{hero}: bad trait {s.trait}"
            assert s.item in data.item_names, f"{hero}: no name for {s.item}"
        assert set(build.talents) == {"10", "15", "20", "25"}, f"{hero}: talents"

    # trait map references real heroes and valid traits
    keys = {h["key"] for h in data.heroes}
    for ehero, traits in data.traits.items():
        assert ehero in keys, f"unknown enemy hero {ehero}"
        for t in traits:
            assert t in TRAITS, f"bad trait {t} for {ehero}"


def test_hero_names_derived_from_heroes_list():
    data = load_build_data()
    assert data.hero_names["npc_dota_hero_zuus"] == "Zeus"
