from datetime import date, timedelta

from api.core.stats import compute_period_comparisons, compute_streaks, summarize


def _h(*entries):
    """Build history list from (iso_date, paragraphs) pairs."""
    return [{"date": d, "paragraphs": p} for d, p in entries]


def _today():
    return date.today().isoformat()


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def test_compute_streaks_empty():
    result = compute_streaks([])
    assert result == {"current_streak": 0, "longest_streak": 0, "best_day_date": "",
                      "best_day_paras": 0}


def test_compute_streaks_single_day_today():
    today = _today()
    result = compute_streaks(_h((today, 5)))
    assert result["current_streak"] == 1
    assert result["longest_streak"] == 1
    assert result["best_day_date"] == today
    assert result["best_day_paras"] == 5


def test_compute_streaks_consecutive_days():
    history = _h(
        (_days_ago(2), 3),
        (_days_ago(1), 5),
        (_today(), 2),
    )
    result = compute_streaks(history)
    assert result["current_streak"] == 3
    assert result["longest_streak"] == 3
    assert result["best_day_paras"] == 5


def test_compute_streaks_gap_breaks_current():
    # days_ago(3), days_ago(2) consecutive; days_ago(1) missing; today present
    history = _h(
        (_days_ago(3), 4),
        (_days_ago(2), 4),
        (_today(), 2),
    )
    result = compute_streaks(history)
    assert result["current_streak"] == 1   # gap on days_ago(1)
    assert result["longest_streak"] == 2   # days_ago(3)+days_ago(2)


def test_compute_streaks_today_no_entry_yesterday_yes():
    history = _h((_days_ago(1), 5))
    result = compute_streaks(history)
    assert result["current_streak"] == 1   # yesterday counts when today absent


def test_compute_streaks_longest_not_current():
    # 3-day run long ago, gap, single day today
    history = _h(
        (_days_ago(18), 10),
        (_days_ago(17), 10),
        (_days_ago(16), 10),
        (_today(), 1),
    )
    result = compute_streaks(history)
    assert result["longest_streak"] == 3
    assert result["current_streak"] == 1   # gap between days_ago(16) and today
    assert result["best_day_paras"] == 10


# ---------------------------------------------------------------------------
# compute_period_comparisons
# ---------------------------------------------------------------------------



def _row(iso, paras=0, chars=0, en=0):
    return {"date": iso, "paragraphs": paras, "chars": chars, "en_words": en}


def test_period_comparisons_today_vs_yesterday():
    today = date(2026, 7, 3)
    history = [_row("2026-07-03", paras=10), _row("2026-07-02", paras=5)]
    result = compute_period_comparisons(history, "paragraphs", today)
    t = result["periods"]["today"]
    assert t["current"] == 10
    assert t["previous"] == 5
    assert t["pct_change"] == 100.0


def test_period_comparisons_week_boundary():
    today = date(2026, 7, 3)
    # 2026-06-27 is day 7 back -> inside current week; 2026-06-26 is day 8 -> previous week
    history = [_row("2026-06-27", paras=3), _row("2026-06-26", paras=7)]
    result = compute_period_comparisons(history, "paragraphs", today)
    w = result["periods"]["week"]
    assert w["current"] == 3
    assert w["previous"] == 7


def test_period_comparisons_zero_previous_gives_none():
    today = date(2026, 7, 3)
    history = [_row("2026-07-03", paras=10)]
    result = compute_period_comparisons(history, "paragraphs", today)
    assert result["periods"]["today"]["pct_change"] is None


def test_period_comparisons_negative_change():
    today = date(2026, 7, 3)
    history = [_row("2026-07-03", paras=4), _row("2026-07-02", paras=8)]
    result = compute_period_comparisons(history, "paragraphs", today)
    assert result["periods"]["today"]["pct_change"] == -50.0


def test_period_comparisons_empty_history():
    result = compute_period_comparisons([], "paragraphs", date(2026, 7, 3))
    for key in ("today", "week", "month"):
        p = result["periods"][key]
        assert p["current"] == 0
        assert p["previous"] == 0
        assert p["pct_change"] is None
    assert result["daily_avg_30"] == 0


def test_period_comparisons_respects_metric():
    today = date(2026, 7, 3)
    history = [_row("2026-07-03", paras=1, chars=500), _row("2026-07-02", paras=1, chars=100)]
    result = compute_period_comparisons(history, "chars", today)
    assert result["periods"]["today"]["current"] == 500
    assert result["periods"]["today"]["pct_change"] == 400.0


def test_period_comparisons_daily_avg_30():
    today = date(2026, 7, 3)
    # 60 paras within last 30 days, plus old data that must not count
    history = [_row("2026-07-01", paras=45), _row("2026-06-10", paras=15),
               _row("2026-01-01", paras=999)]
    result = compute_period_comparisons(history, "paragraphs", today)
    assert result["daily_avg_30"] == 2.0  # 60 / 30


def test_summarize_windows_end_today():
    today = date(2026, 10, 13)
    history = [
        {"date": "2026-10-13", "paragraphs": 1, "chars": 10, "en_words": 2},
        {"date": "2026-10-07", "paragraphs": 2, "chars": 20, "en_words": 4},  # 7th day back
        {"date": "2026-10-06", "paragraphs": 4, "chars": 40, "en_words": 8},
        {"date": "2026-09-01", "paragraphs": 8, "chars": 80, "en_words": 16},
    ]
    s = summarize(history, today)
    assert s["today"] == {"paragraphs": 1, "chars": 10, "en_words": 2}
    assert s["week"]["paragraphs"] == 3 and s["month"]["paragraphs"] == 7
    assert s["alltime"]["paragraphs"] == 15
