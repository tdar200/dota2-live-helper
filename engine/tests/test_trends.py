"""Unit tests for app.trends.compute_trends (pure, no I/O)."""
from app.personal_stats import PersonalStats, HeroWR, MatchRecord
from app.trends import compute_trends, rank_name

DAY = 86400
NOW = 1_800_000_000  # fixed "now" for recency windows


def _rec(mid, days_ago, win, k=5, d=5, a=5, dur=2000, party=1, rank=14):
    return MatchRecord(
        match_id=mid, start_time=NOW - days_ago * DAY, duration=dur, win=win,
        hero="npc_dota_hero_sniper", kills=k, deaths=d, assists=a,
        party_size=party, game_mode=22, lobby_type=7, average_rank=rank,
    )


def _stats(history, heroes=None):
    return PersonalStats(
        has_data=True, account_id=1,
        heroes=heroes or {}, items={}, match_history=history,
    )


def test_rank_name():
    assert rank_name(14) == "Herald"
    assert rank_name(23) == "Guardian"
    assert rank_name(None) is None
    assert rank_name(80) == "Immortal"


def test_empty_history_degrades():
    r = compute_trends(_stats([]), NOW)
    assert r.has_data is False


def test_totals_and_streak_newest_first():
    # newest-first: W W L W L  -> current streak +2, 3/5 wins
    hist = [_rec(5, 1, True), _rec(4, 2, True), _rec(3, 3, False),
            _rec(2, 4, True), _rec(1, 5, False)]
    r = compute_trends(_stats(hist), NOW)
    assert r.has_data is True
    assert r.total_games == 5 and r.total_wins == 3
    assert r.winrate == 0.6
    assert r.current_streak == 2
    assert r.recent_results == [True, True, False, True, False]
    # chronological order (oldest->newest): L W L W W -> longest win run 2, loss run 1
    assert r.longest_win_streak == 2
    assert r.longest_loss_streak == 1


def test_loss_streak_sign():
    hist = [_rec(3, 1, False), _rec(2, 2, False), _rec(1, 3, True)]
    r = compute_trends(_stats(hist), NOW)
    assert r.current_streak == -2  # two fresh losses


def test_activity_windows():
    hist = [_rec(1, 1, True), _rec(2, 3, False), _rec(3, 10, True), _rec(4, 40, False)]
    r = compute_trends(_stats(hist), NOW)
    assert r.games_last_7d == 2     # days_ago 1 and 3
    assert r.games_last_30d == 3    # 1, 3, 10


def test_kda_and_undecided_skipped():
    # an undecided match (win=None) must not count toward win totals
    hist = [_rec(3, 1, True, k=10, d=2, a=8),
            _rec(2, 2, False, k=2, d=9, a=3),
            MatchRecord(match_id=1, start_time=NOW - 3 * DAY, win=None)]
    r = compute_trends(_stats(hist), NOW)
    assert r.total_games == 2       # undecided excluded
    assert r.avg_kills == 6.0       # (10+2)/2
    assert r.kda_ratio == round((12 + 11) / 11, 2)


def test_duration_and_party_splits():
    hist = [_rec(1, 1, True, dur=1800, party=1),    # short solo win
            _rec(2, 2, False, dur=3000, party=2),   # long party loss
            _rec(3, 3, True, dur=2600, party=1)]    # long solo win
    r = compute_trends(_stats(hist), NOW)
    short = next(s for s in r.duration_split if s.label.startswith("short"))
    long_ = next(s for s in r.duration_split if s.label.startswith("long"))
    assert short.games == 1 and short.winrate == 1.0
    assert long_.games == 2 and long_.winrate == 0.5
    solo = next(s for s in r.party_split if s.label == "solo")
    assert solo.games == 2


def test_bracket_movement():
    # oldest games Herald (14), recent games Guardian (23) -> climbing
    hist = [_rec(4, 1, True, rank=23), _rec(3, 2, True, rank=22),
            _rec(2, 30, False, rank=14), _rec(1, 31, False, rank=13)]
    r = compute_trends(_stats(hist), NOW)
    assert r.rank_start == "Herald"
    assert r.rank_now == "Guardian"


def test_all_undecided_history_degrades():
    # non-empty history but every match unparsed (win None) -> no usable data
    hist = [MatchRecord(match_id=i, start_time=NOW - i * DAY, win=None) for i in range(1, 4)]
    r = compute_trends(_stats(hist), NOW)
    assert r.has_data is False


def test_malformed_start_time_does_not_crash():
    # a schema-valid but absurd start_time must not 500 the report
    hist = [
        MatchRecord(match_id=1, start_time=10**19, win=True, kills=5, deaths=2, assists=3),
        _rec(2, 2, False),
    ]
    r = compute_trends(_stats(hist), NOW)   # must not raise
    assert r.has_data is True
    assert r.total_games == 2               # both decided still counted
    # the bad-timestamp row is simply absent from monthly buckets
    assert all(b.games >= 1 for b in r.monthly)


def test_recent_kda_stays_within_recent_window():
    # newest match lacks KDA; an OUTLIER sits just past the recent-20 window.
    # recent_kda must ignore the outlier (old sliding bug would pull it in).
    hist = [MatchRecord(match_id=100, start_time=NOW - 1 * DAY, win=True)]  # no KDA
    for i in range(1, 20):  # 19 normal decided games, 2/2/2
        hist.append(MatchRecord(match_id=i, start_time=NOW - (i + 1) * DAY, win=True,
                                kills=2, deaths=2, assists=2))
    hist.append(MatchRecord(match_id=999, start_time=NOW - 40 * DAY, win=True,
                            kills=100, deaths=1, assists=0))  # outlier, 21st decided
    r = compute_trends(_stats(hist), NOW)
    assert r.recent_kda_ratio == 2.0   # (2+2)/2, outlier excluded


def test_best_worst_heroes_from_aggregate():
    heroes = {
        "npc_dota_hero_sniper": HeroWR(games=24, wins=16, winrate=0.667),
        "npc_dota_hero_huskar": HeroWR(games=46, wins=20, winrate=0.435),
        "npc_dota_hero_tiny": HeroWR(games=5, wins=5, winrate=1.0),  # < min games
    }
    hist = [_rec(1, 1, True)]
    r = compute_trends(_stats(hist, heroes), NOW)
    assert r.best_heroes[0].hero == "npc_dota_hero_sniper"
    assert r.worst_heroes[0].hero == "npc_dota_hero_huskar"
    # tiny sample excluded from best/worst
    assert all(h.hero != "npc_dota_hero_tiny" for h in r.best_heroes)
