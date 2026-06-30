from app.modules.timings import PeriodicEvent, next_occurrences


def ev(name, first, interval, end=None, cat="test"):
    return PeriodicEvent(name=name, first_spawn_s=first, interval_s=interval, end_s=end, category=cat)


def test_periodic_before_first_spawn():
    hits = next_occurrences(0, [ev("bounty", 0, 180)])
    assert hits[0].next_time_s == 0
    assert hits[0].seconds_until == 0


def test_periodic_midcycle_rounds_up():
    hits = next_occurrences(200, [ev("bounty", 0, 180)])
    # spawns at 0,180,360 -> soonest >= 200 is 360
    assert hits[0].next_time_s == 360
    assert hits[0].seconds_until == 160


def test_oneshot_in_future():
    hits = next_occurrences(100, [ev("first_neutral", 420, None)])
    assert hits[0].next_time_s == 420
    assert hits[0].seconds_until == 320


def test_oneshot_in_past_is_dropped():
    hits = next_occurrences(500, [ev("first_neutral", 420, None)])
    assert hits == []


def test_window_end_drops_event():
    # water runes only at 120 and 240, window ends at 240
    hits = next_occurrences(300, [ev("water", 120, 120, end=240)])
    assert hits == []


def test_sorted_by_soonest():
    events = [ev("a", 0, 300), ev("b", 0, 120)]
    hits = next_occurrences(50, events)
    assert [h.name for h in hits] == ["b", "a"]  # b next at 120, a next at 300


from app.timing_constants import GAME_EVENTS


def test_constants_produce_sorted_upcoming_events_at_5min():
    hits = next_occurrences(300, GAME_EVENTS)  # at clock 5:00
    assert hits, "expected upcoming events at 5:00"
    # sorted ascending and all in the future-or-now
    assert all(h.seconds_until >= 0 for h in hits)
    assert hits == sorted(hits, key=lambda h: h.seconds_until)
    names = {h.name for h in hits}
    assert "Power rune" in names  # next power rune at 6:00 -> 60s away
