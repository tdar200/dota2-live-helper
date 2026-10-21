"""Personal trends computed from the match-history slice of the personal cache.

Pure + degrade-safe: given a PersonalStats (which may have an empty history),
produce a TrendsReport. No network, no I/O. The engine exposes it at GET /trends;
`now_ts` is injected so recency windows are testable.
"""
import datetime
from pydantic import BaseModel, Field
from app.personal_stats import PersonalStats, MatchRecord

_RECENT_N = 20
_LONG_GAME_S = 35 * 60  # 35 min divides "short stomp" from "long grind"
_MEDALS = {1: "Herald", 2: "Guardian", 3: "Crusader", 4: "Archon",
           5: "Legend", 6: "Ancient", 7: "Divine", 8: "Immortal"}


def rank_name(avg_rank: int | None) -> str | None:
    """OpenDota average_rank (medal*10 + stars) -> medal name, e.g. 14 -> 'Herald'."""
    if avg_rank is None:
        return None
    medal = avg_rank // 10
    return _MEDALS.get(medal)


class Bucket(BaseModel):
    period: str
    games: int
    wins: int
    winrate: float


class Split(BaseModel):
    label: str
    games: int
    wins: int
    winrate: float | None = None


class HeroLine(BaseModel):
    hero: str
    games: int
    winrate: float


class TrendsReport(BaseModel):
    has_data: bool = False
    total_games: int = 0
    total_wins: int = 0
    winrate: float | None = None
    # recency
    recent_results: list[bool] = Field(default_factory=list)  # newest-first, last N
    recent_winrate: float | None = None
    current_streak: int = 0            # +n win streak / -n loss streak
    longest_win_streak: int = 0
    longest_loss_streak: int = 0
    games_last_7d: int = 0
    games_last_30d: int = 0
    # combat
    avg_kills: float | None = None
    avg_deaths: float | None = None
    avg_assists: float | None = None
    kda_ratio: float | None = None
    recent_kda_ratio: float | None = None
    # splits
    monthly: list[Bucket] = Field(default_factory=list)
    duration_split: list[Split] = Field(default_factory=list)
    party_split: list[Split] = Field(default_factory=list)
    # bracket movement
    rank_medal: str | None = None
    rank_start: str | None = None
    rank_now: str | None = None
    # heroes (from the all-time per-hero aggregate)
    most_played: list[HeroLine] = Field(default_factory=list)
    best_heroes: list[HeroLine] = Field(default_factory=list)
    worst_heroes: list[HeroLine] = Field(default_factory=list)


def _winrate(w: int, g: int) -> float | None:
    return round(w / g, 4) if g else None


def _split(label, recs) -> Split:
    decided = [r for r in recs if r.win is not None]
    w = sum(1 for r in decided if r.win)
    return Split(label=label, games=len(decided), wins=w, winrate=_winrate(w, len(decided)))


def _hero_lines(stats: PersonalStats, min_games: int, key, reverse: bool, n: int) -> list[HeroLine]:
    rows = [HeroLine(hero=k, games=v.games, winrate=v.winrate or 0.0)
            for k, v in stats.heroes.items() if v.games >= min_games and v.winrate is not None]
    rows.sort(key=key, reverse=reverse)
    return rows[:n]


def compute_trends(stats: PersonalStats, now_ts: int) -> TrendsReport:
    hist = stats.match_history
    decided = [m for m in hist if m.win is not None]          # newest-first
    # No decided games (empty, or only unparsed/very-recent rows) -> degrade like
    # an empty history so the UI shows "No history yet", not a misleading 0-0.
    if not decided:
        return TrendsReport(has_data=False)

    total_g = len(decided)
    total_w = sum(1 for m in decided if m.win)

    # recency / streaks (hist is newest-first)
    recent = decided[:_RECENT_N]
    recent_results = [bool(m.win) for m in recent]
    recent_w = sum(recent_results)

    current_streak = 0
    for m in decided:
        if current_streak == 0:
            current_streak = 1 if m.win else -1
        elif (current_streak > 0) == bool(m.win):
            current_streak += 1 if m.win else -1
        else:
            break

    longest_w = longest_l = cur = 0
    for m in reversed(decided):  # chronological for streak lengths
        if m.win:
            cur = cur + 1 if cur > 0 else 1
        else:
            cur = cur - 1 if cur < 0 else -1
        longest_w = max(longest_w, cur)
        longest_l = min(longest_l, cur)

    # activity windows
    g7 = sum(1 for m in hist if m.start_time and m.start_time >= now_ts - 7 * 86400)
    g30 = sum(1 for m in hist if m.start_time and m.start_time >= now_ts - 30 * 86400)

    # combat
    with_kda = [m for m in decided if m.kills is not None and m.deaths is not None and m.assists is not None]
    def _kda_ratio(recs):
        if not recs:
            return None
        k = sum(m.kills for m in recs); d = sum(m.deaths for m in recs); a = sum(m.assists for m in recs)
        return round((k + a) / max(d, 1), 2)
    avg_k = round(sum(m.kills for m in with_kda) / len(with_kda), 1) if with_kda else None
    avg_d = round(sum(m.deaths for m in with_kda) / len(with_kda), 1) if with_kda else None
    avg_a = round(sum(m.assists for m in with_kda) / len(with_kda), 1) if with_kda else None

    # monthly buckets (chronological, last 12 with data)
    by_month: dict[str, list[MatchRecord]] = {}
    for m in decided:
        if m.start_time is None:
            continue
        try:
            period = datetime.datetime.fromtimestamp(m.start_time, datetime.timezone.utc).strftime("%Y-%m")
        except (OverflowError, OSError, ValueError):
            continue  # corrupt timestamp -> skip this row, keep the report alive
        by_month.setdefault(period, []).append(m)
    monthly = []
    for period in sorted(by_month)[-12:]:
        recs = by_month[period]
        w = sum(1 for m in recs if m.win)
        monthly.append(Bucket(period=period, games=len(recs), wins=w, winrate=_winrate(w, len(recs))))

    # duration + party splits
    short = [m for m in decided if m.duration is not None and m.duration < _LONG_GAME_S]
    long_ = [m for m in decided if m.duration is not None and m.duration >= _LONG_GAME_S]
    duration_split = [_split("short (<35m)", short), _split("long (35m+)", long_)]
    solo = [m for m in decided if m.party_size == 1]
    party = [m for m in decided if m.party_size is not None and m.party_size > 1]
    party_split = [_split("solo", solo), _split("party", party)]

    # bracket movement (chronological: oldest vs recent average_rank)
    ranked = [m for m in reversed(decided) if m.average_rank]  # chronological, has rank
    rank_start = rank_now = rank_medal = None
    if ranked:
        head = ranked[: max(1, len(ranked) // 5)]
        tail = ranked[-max(1, len(ranked) // 5):]
        rank_start = rank_name(round(sum(m.average_rank for m in head) / len(head)))
        rank_now = rank_name(round(sum(m.average_rank for m in tail) / len(tail)))
        rank_medal = rank_now

    return TrendsReport(
        has_data=True,
        total_games=total_g, total_wins=total_w, winrate=_winrate(total_w, total_g),
        recent_results=recent_results, recent_winrate=_winrate(recent_w, len(recent)),
        current_streak=current_streak, longest_win_streak=longest_w, longest_loss_streak=-longest_l,
        games_last_7d=g7, games_last_30d=g30,
        avg_kills=avg_k, avg_deaths=avg_d, avg_assists=avg_a,
        kda_ratio=_kda_ratio(with_kda),
        recent_kda_ratio=_kda_ratio([m for m in recent
                                     if m.kills is not None and m.deaths is not None and m.assists is not None]),
        monthly=monthly, duration_split=duration_split, party_split=party_split,
        rank_medal=rank_medal, rank_start=rank_start, rank_now=rank_now,
        most_played=_hero_lines(stats, 1, lambda h: h.games, True, 6),
        best_heroes=_hero_lines(stats, 15, lambda h: h.winrate, True, 6),
        worst_heroes=_hero_lines(stats, 15, lambda h: h.winrate, False, 6),
    )
