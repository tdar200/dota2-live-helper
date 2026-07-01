from app.state import GameState, MapState, HeroState, PlayerState


def parse_gsi(raw: dict) -> GameState:
    m = raw.get("map", {}) or {}
    h = raw.get("hero", {}) or {}
    p = raw.get("player", {}) or {}
    items_obj = raw.get("items", {}) or {}

    items: list[str] = []
    for i in range(9):  # slot0..slot8 are inventory
        slot = items_obj.get(f"slot{i}")
        if slot and slot.get("name") and slot["name"] != "empty":
            items.append(slot["name"])

    map_state = MapState(
        clock_time=m.get("clock_time"),
        game_state=m.get("game_state"),
        daytime=m.get("daytime"),
    )
    return GameState(
        clock_time=m.get("clock_time"),
        map=map_state,
        hero=HeroState(
            name=h.get("name"),
            level=h.get("level"),
            alive=h.get("alive"),
            buyback_cost=h.get("buyback_cost"),
            buyback_cooldown=h.get("buyback_cooldown"),
            respawn_seconds=h.get("respawn_seconds"),
        ),
        player=PlayerState(
            gold=p.get("gold"),
            gpm=p.get("gpm"),
            xpm=p.get("xpm"),
        ),
        items=items,
    )
