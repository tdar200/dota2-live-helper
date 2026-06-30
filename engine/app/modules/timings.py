from pydantic import BaseModel


class PeriodicEvent(BaseModel):
    name: str
    first_spawn_s: int
    interval_s: int | None = None  # None => one-shot
    end_s: int | None = None       # last second the event can occur (inclusive)
    category: str = "general"


class TimingHit(BaseModel):
    name: str
    category: str
    next_time_s: int
    seconds_until: int


def _next_time(now_s: int, e: PeriodicEvent) -> int | None:
    if e.interval_s is None:
        t = e.first_spawn_s
        return t if t >= now_s else None
    if now_s <= e.first_spawn_s:
        t = e.first_spawn_s
    else:
        elapsed = now_s - e.first_spawn_s
        steps = (elapsed + e.interval_s - 1) // e.interval_s  # ceil
        t = e.first_spawn_s + steps * e.interval_s
    if e.end_s is not None and t > e.end_s:
        return None
    return t


def next_occurrences(now_s: int, events: list[PeriodicEvent]) -> list[TimingHit]:
    hits: list[TimingHit] = []
    for e in events:
        t = _next_time(now_s, e)
        if t is None:
            continue
        hits.append(
            TimingHit(
                name=e.name,
                category=e.category,
                next_time_s=t,
                seconds_until=t - now_s,
            )
        )
    hits.sort(key=lambda h: h.seconds_until)
    return hits
