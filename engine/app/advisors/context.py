from dataclasses import dataclass, field
from app.state import GameState


@dataclass
class AdviceContext:
    state: GameState
    horizon_s: int = 600
    limit: int = 6
    enemy_heroes: list[str] = field(default_factory=list)
    build_db: dict = field(default_factory=dict)
    trait_db: dict = field(default_factory=dict)
    item_names: dict = field(default_factory=dict)
    hero_names: dict = field(default_factory=dict)
    ally_heroes: list[str] = field(default_factory=list)
    matchup_data: object | None = None
    net_worth_lead: int | None = None
    roshan_dead_clock: int | None = None
    winprob_table: object | None = None
    item_build_db: dict = field(default_factory=dict)
    # item_key -> gold cost, for live net-worth estimation (empty is fine)
    item_costs: dict = field(default_factory=dict)
    hero_meta_db: dict = field(default_factory=dict)
    # hero_key -> HeroWR  (your personal per-hero win-rate)
    personal_hero_db: dict = field(default_factory=dict)
    # hero_key -> {item_key -> ItemWR}  (your personal per-item win-rate)
    personal_item_db: dict = field(default_factory=dict)
