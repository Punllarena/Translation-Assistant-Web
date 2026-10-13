"""Statistics helpers, from the desktop core.py (compute_streaks, compute_period_comparisons,
verbatim) plus summarize, which replaces the desktop get_summary_stats's four queries."""

from datetime import date, timedelta

METRICS = ("paragraphs", "chars", "en_words")


def compute_streaks(history: list[dict], today: date | None = None) -> dict:
    """
    Compute current streak, longest streak, and best day from daily stats history.

    Args:
        history: list of dicts with keys "date" (ISO string "YYYY-MM-DD") and
                 "paragraphs" (int).
        today: reference date for the "current" streak; defaults to date.today().
               Callers using UTC-bucketed history should pass a UTC date.

    Returns:
        dict with keys:
        - current_streak: int (active or ended yesterday)
        - longest_streak: int (all time)
        - best_day_date: str (ISO date, empty if no data)
        - best_day_paras: int (max paragraphs, 0 if no data)
    """
    active_set = {r["date"] for r in history if r["paragraphs"] > 0}
    active = sorted(active_set)

    if not active:
        return {"current_streak": 0, "longest_streak": 0, "best_day_date": "", "best_day_paras": 0}

    longest = 1
    run = 1
    for i in range(1, len(active)):
        prev = date.fromisoformat(active[i - 1])
        curr = date.fromisoformat(active[i])
        if (curr - prev).days == 1:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 1

    if today is None:
        today = date.today()
    check = today if today.isoformat() in active_set else today - timedelta(days=1)
    current = 0
    while check.isoformat() in active_set:
        current += 1
        check -= timedelta(days=1)

    best = max(history, key=lambda r: r["paragraphs"])
    return {
        "current_streak": current,
        "longest_streak": longest,
        "best_day_date": best["date"],
        "best_day_paras": best["paragraphs"],
    }


def compute_period_comparisons(history: list[dict], metric: str, today: date) -> dict:
    """
    Compare current vs previous periods for one metric from daily stats history.

    Args:
        history: rows shaped like Database.get_all_daily_stats() output —
                 dicts with "date" (ISO string) and per-metric int values.
        metric: "paragraphs" | "chars" | "en_words".
        today: reference date for period windows.

    Returns:
        dict with:
        - periods: {"today"|"week"|"month": {"current", "previous", "pct_change"}}
          where pct_change is a float percentage or None if previous == 0.
          today = 1-day window vs yesterday; week = last 7 days vs prior 7;
          month = last 30 days vs prior 30 (all windows include their end day).
        - daily_avg_30: float, last-30-day total divided by 30.
    """
    by_date = {date.fromisoformat(r["date"]): r.get(metric, 0) for r in history}

    def _total(start: date, end: date) -> int:
        return sum(v for d, v in by_date.items() if start <= d <= end)

    periods = {}
    for key, days in (("today", 1), ("week", 7), ("month", 30)):
        cur_start = today - timedelta(days=days - 1)
        current = _total(cur_start, today)
        prev_end = cur_start - timedelta(days=1)
        previous = _total(prev_end - timedelta(days=days - 1), prev_end)
        pct = None if previous == 0 else (current - previous) / previous * 100
        periods[key] = {"current": current, "previous": previous, "pct_change": pct}

    daily_avg_30 = _total(today - timedelta(days=29), today) / 30
    return {"periods": periods, "daily_avg_30": daily_avg_30}




def summarize(history: list[dict], today: date) -> dict[str, dict[str, int]]:
    """The desktop get_summary_stats windows — today, the last 7 days, the last 30 days
    (each ending today), and all time — summed from the daily rows."""
    def total(days: int | None) -> dict[str, int]:
        start = "" if days is None else (today - timedelta(days=days - 1)).isoformat()
        rows = [r for r in history if start <= r["date"] <= today.isoformat()]
        return {m: sum(r[m] for r in rows) for m in METRICS}

    return {"today": total(1), "week": total(7), "month": total(30), "alltime": total(None)}
