from app.state import GameState, MapState, HeroState, PlayerState, AbilityState

# GSI ability slots that carry no castable spell — never surfaced.
_SKIP_ABILITIES = {"", "empty", "generic_hidden"}


def _as_bool(v):
    """GSI sends 0/1 ints or bools for flags; normalise to bool, pass None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return bool(v)


# Steam64 -> Steam32 (Dota account id) offset.
_STEAM64_BASE = 76561197960265728


def _account_id(p: dict) -> int | None:
    """The player's 32-bit Dota account id from a GSI `player` block.

    GSI usually sends `accountid` directly (as a numeric string); if only
    `steamid` (64-bit) is present, derive the 32-bit id from it.
    """
    acc = p.get("accountid")
    if acc is not None:
        try:
            return int(acc)
        except (TypeError, ValueError):
            return None
    steam = p.get("steamid")
    if steam is not None:
        try:
            return int(steam) - _STEAM64_BASE
        except (TypeError, ValueError):
            return None
    return None


def _parse_abilities(raw: dict) -> list[AbilityState]:
    """Scan ability0..29 faithfully (keep talents/passives); skip empties.

    Local parse only — no network. The advisor decides what to surface.
    """
    ab_obj = raw.get("abilities", {}) or {}
    out: list[AbilityState] = []
    for i in range(30):
        a = ab_obj.get(f"ability{i}")
        if not a:
            continue
        name = a.get("name")
        if not name or name in _SKIP_ABILITIES:
            continue
        out.append(
            AbilityState(
                name=name,
                level=a.get("level"),
                can_cast=_as_bool(a.get("can_cast")),
                passive=_as_bool(a.get("passive")),
                ability_active=_as_bool(a.get("ability_active")),
                cooldown=a.get("cooldown"),
                ultimate=bool(a.get("ultimate", False)),
                charges=a.get("charges"),
                max_charges=a.get("max_charges"),
            )
        )
    return out


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
            aghanims_scepter=_as_bool(h.get("aghanims_scepter")),
            aghanims_shard=_as_bool(h.get("aghanims_shard")),
            abilities=_parse_abilities(raw),
        ),
        player=PlayerState(
            gold=p.get("gold"),
            gpm=p.get("gpm"),
            xpm=p.get("xpm"),
            last_hits=p.get("last_hits"),
            account_id=_account_id(p),
        ),
        items=items,
    )
