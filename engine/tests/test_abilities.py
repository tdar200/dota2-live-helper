from app.state import GameState, HeroState, AbilityState
from app.advisors.context import AdviceContext
from app.advisors import abilities


def _ctx(hero: HeroState) -> AdviceContext:
    state = GameState()
    state.hero = hero
    return AdviceContext(state=state)


def test_unavailable_when_absent():
    adv = abilities.advise(_ctx(HeroState(name="npc_dota_hero_sniper")))
    assert adv.available is False
    assert adv.ultimate is None
    assert adv.key_spells == []
    assert adv.headline is None


def test_ult_ready_headline_and_key_spells_filtered():
    hero = HeroState(
        name="npc_dota_hero_sniper",
        aghanims_scepter=True,
        aghanims_shard=False,
        abilities=[
            AbilityState(name="sniper_shrapnel", level=1, passive=False,
                         cooldown=0, charges=3, ultimate=False),
            AbilityState(name="sniper_headshot", level=1, passive=True, ultimate=False),
            AbilityState(name="special_bonus_attack_speed_30", level=1,
                         passive=True, ultimate=False),
            AbilityState(name="sniper_assassinate", level=1, passive=False,
                         can_cast=True, cooldown=0, ultimate=True),
        ],
    )
    adv = abilities.advise(_ctx(hero))
    assert adv.available is True
    assert adv.headline == "ULT READY"
    assert adv.ultimate is not None and adv.ultimate.ready is True
    names = [s.name for s in adv.key_spells]
    assert "sniper_shrapnel" in names            # charge spell surfaced
    assert "sniper_headshot" not in names        # passive excluded
    assert "special_bonus_attack_speed_30" not in names  # talent excluded
    assert "sniper_assassinate" not in names     # ult not in key_spells
    assert adv.aghanims_scepter is True
    assert adv.aghanims_shard is False


def test_ult_on_cooldown_headline():
    hero = HeroState(
        name="x",
        abilities=[
            AbilityState(name="ult", level=3, passive=False,
                         can_cast=False, cooldown=14, ultimate=True),
        ],
    )
    adv = abilities.advise(_ctx(hero))
    assert adv.available is True
    assert adv.ultimate is not None and adv.ultimate.ready is False
    assert adv.headline == "ULT 14s"


def test_unlearned_l0_ult_absent():
    hero = HeroState(
        name="x",
        abilities=[
            AbilityState(name="ult", level=0, passive=False,
                         cooldown=0, ultimate=True),
        ],
    )
    adv = abilities.advise(_ctx(hero))
    assert adv.available is True
    assert adv.ultimate is None
    assert adv.headline is None


def test_key_spells_capped_at_three():
    hero = HeroState(
        name="x",
        abilities=[
            AbilityState(name=f"q{i}", level=1, passive=False, cooldown=0,
                         ultimate=False)
            for i in range(5)
        ],
    )
    adv = abilities.advise(_ctx(hero))
    assert len(adv.key_spells) == 3
