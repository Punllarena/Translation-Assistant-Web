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


class OllamaOutcomes(BaseModel):
    used: int
    edited: int
    ignored: int


class OllamaRun(BaseModel):
    job_id: int
    date: str  # ISO date in the requested zone
    chapters: int
    lines: int
    duration_s: float | None
    tokens_per_s: float | None
    lines_per_hour: float | None
    s_per_chunk: float | None
    prompt_tokens: int
    output_tokens: int


class OllamaModelStats(BaseModel):
    model: str
    preset: str
    chunk_lines: int
    context_lines: int
    runs: int
    tokens_per_s: float | None
    prompt_tokens: int
    output_tokens: int
    s_per_chunk: float | None
    used_or_edited_pct: float | None


class OllamaTokenTotals(BaseModel):
    requests: int  # every request, failed ones included
    prompt_tokens: int  # input
    output_tokens: int
    total_tokens: int
    seconds: float  # time Ollama spent answering
    prompt_tokens_per_s: float | None  # prompt processing speed


class OllamaTokens(BaseModel):
    d30: OllamaTokenTotals
    all: OllamaTokenTotals


class OllamaStatsOut(BaseModel):
    tokens_per_s_30d: float | None
    lines_30d: int
    chapters_30d: int
    outcomes: OllamaOutcomes
    retry_rate_30d: float | None
    tokens: OllamaTokens
    runs: list[OllamaRun]  # last 60 finished runs, newest first
    by_model: list[OllamaModelStats]
