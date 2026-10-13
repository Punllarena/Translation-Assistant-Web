from datetime import date

from pydantic import BaseModel


class Totals(BaseModel):
    paragraphs: int
    chars: int
    en_words: int


class DayStats(Totals):
    date: str  # ISO date in the requested zone


class Streaks(BaseModel):
    current_streak: int
    longest_streak: int
    best_day_date: str
    best_day_paras: int


class PeriodChange(BaseModel):
    current: int
    previous: int
    pct_change: float | None


class Comparison(BaseModel):
    periods: dict[str, PeriodChange]  # today | week | month
    daily_avg_30: float


class SeriesStats(Totals):
    series_id: int
    series: str
    chapters: int


class StatsOut(BaseModel):
    today: date
    daily: list[DayStats]  # oldest first; days with no translations are absent
    summary: dict[str, Totals]  # today | week | month | alltime
    streaks: Streaks
    comparisons: dict[str, Comparison]  # per metric
    series: list[SeriesStats]
