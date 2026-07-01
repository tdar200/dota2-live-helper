from pydantic import BaseModel, Field


class MapState(BaseModel):
    clock_time: int | None = None
    game_state: str | None = None
    daytime: bool | None = None


class HeroState(BaseModel):
    name: str | None = None
    level: int | None = None
    alive: bool | None = None
    buyback_cost: int | None = None
    buyback_cooldown: int | None = None


class PlayerState(BaseModel):
    gold: int | None = None
    gpm: int | None = None
    xpm: int | None = None


class GameState(BaseModel):
    clock_time: int | None = None
    map: MapState = Field(default_factory=MapState)
    hero: HeroState = Field(default_factory=HeroState)
    player: PlayerState = Field(default_factory=PlayerState)
    items: list[str] = Field(default_factory=list)
    enemy_heroes: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)

    def update_from_raw(self, raw: dict) -> None:
        from app.gsi import parse_gsi

        fresh = parse_gsi(raw)
        self.clock_time = fresh.clock_time
        self.map = fresh.map
        self.hero = fresh.hero
        self.player = fresh.player
        self.items = fresh.items
        self.raw = raw
