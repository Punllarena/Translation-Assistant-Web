from datetime import UTC, datetime, timedelta

from api.models import Document, Job, OllamaChunk


def _chunk(db, user, doc, **kw):
    fields = dict(
        user_id=user.id, series_id=doc.series_id if doc else None,
        document_id=doc.id if doc else None, source="run", ok=True, clamped=False, depth=0,
        model="qwen3:14b", preset="small", chunk_lines=12, context_lines=5, first_line=0,
        last_line=1, asked=2, prompt_tokens=10, output_tokens=100, eval_ms=1000, total_ms=2000,
    )
    fields.update(kw)
    chunk = OllamaChunk(**fields)
    db.add(chunk)
    db.flush()
    return chunk


def _job(db, user, **kw):
    job = Job(user_id=user.id, kind="ollama_run", state="done", **kw)
    db.add(job)
    db.flush()
    return job


def test_tokens_per_second_and_retry_rate(app_client, me, make_doc, db):
    doc, doc2 = make_doc(me, ["a"]), make_doc(me, ["b"])
    _chunk(db, me, doc, output_tokens=100, eval_ms=1000, asked=3)
    _chunk(db, me, doc2, output_tokens=300, eval_ms=1000, asked=4)
    _chunk(db, me, doc, ok=False, output_tokens=999, eval_ms=1, asked=9)
    _chunk(db, me, doc, eval_ms=None, asked=1, created_at=datetime.now(UTC) - timedelta(days=40))
    body = app_client.get("/stats/ollama").json()
    assert body["tokens_per_s_30d"] == 200.0
    assert body["lines_30d"] == 7 and body["chapters_30d"] == 2
    assert body["retry_rate_30d"] == 1 / 3


def test_empty_is_none(app_client, me):
    body = app_client.get("/stats/ollama").json()
    assert body["tokens_per_s_30d"] is None and body["retry_rate_30d"] is None
    assert body["runs"] == [] and body["by_model"] == []
    assert body["outcomes"] == {"used": 0, "edited": 0, "ignored": 0}


def test_outcomes_survive_flush_and_chapter_delete(app_client, me, make_doc, db):
    doc = make_doc(me, ["a"])
    _chunk(db, me, doc, used_count=3, edited_count=1, ignored_count=2)
    db.delete(db.get(Document, doc.id))
    db.flush()
    body = app_client.get("/stats/ollama").json()
    assert body["outcomes"] == {"used": 3, "edited": 1, "ignored": 2}
    row = body["by_model"][0]
    assert row["used_or_edited_pct"] == 4 / 6 * 100
    assert (row["model"], row["preset"], row["chunk_lines"], row["context_lines"]) == (
        "qwen3:14b", "small", 12, 5)
    assert row["runs"] == 0 and row["s_per_chunk"] == 2.0


def test_runs_bucket_in_viewer_zone(app_client, me, make_doc, db):
    doc = make_doc(me, ["a"])
    start = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)
    job = _job(db, me, started_at=start, finished_at=start + timedelta(hours=2),
               result_json={"lines": 10, "chunks": 2})
    _chunk(db, me, doc, job_id=job.id, output_tokens=50, eval_ms=500, total_ms=3000)
    _chunk(db, me, doc, job_id=job.id, output_tokens=150, eval_ms=1500, total_ms=1000)
    _job(db, me)  # unfinished: not listed
    utc = app_client.get("/stats/ollama", params={"tz": "UTC"}).json()
    tokyo = app_client.get("/stats/ollama", params={"tz": "Asia/Tokyo"}).json()
    assert utc["runs"][0]["date"] == "2026-01-01" and tokyo["runs"][0]["date"] == "2026-01-02"
    run = utc["runs"][0]
    assert len(utc["runs"]) == 1
    assert run["job_id"] == job.id and run["chapters"] == 1 and run["lines"] == 10
    assert run["duration_s"] == 7200 and run["lines_per_hour"] == 5.0
    assert run["tokens_per_s"] == 100.0 and run["s_per_chunk"] == 2.0
    assert utc["by_model"][0]["runs"] == 1
    assert app_client.get("/stats/ollama", params={"tz": "Nope/Zone"}).status_code == 422


def test_only_own_chunks(app_client, me, make_user, make_doc, db):
    other = make_user(email="o@example.com")
    theirs = make_doc(other, ["a"])
    _chunk(db, other, theirs, used_count=5)
    _job(db, other, finished_at=datetime.now(UTC), result_json={"lines": 1})
    body = app_client.get("/stats/ollama").json()
    assert body["lines_30d"] == 0 and body["runs"] == [] and body["by_model"] == []
    assert body["outcomes"]["used"] == 0


def test_token_totals_30_days_and_all_time(app_client, me, make_user, make_doc, db):
    doc = make_doc(me, ["a"])
    _chunk(db, me, doc, prompt_tokens=500, output_tokens=100, prompt_ms=250, total_ms=2000)
    _chunk(db, me, None, ok=False, source="manual", prompt_tokens=300, output_tokens=50,
           prompt_ms=None, total_ms=1000)
    _chunk(db, me, doc, prompt_tokens=1000, output_tokens=400, prompt_ms=500, total_ms=4000,
           created_at=datetime.now(UTC) - timedelta(days=40))
    other = make_user(email="other@example.com")
    _chunk(db, other, make_doc(other, ["b"]), prompt_tokens=9999)
    t = app_client.get("/stats/ollama").json()["tokens"]
    assert t["d30"] == {"requests": 2, "prompt_tokens": 800, "output_tokens": 150,
                        "total_tokens": 950, "seconds": 3.0, "prompt_tokens_per_s": 2000.0}
    assert t["all"]["requests"] == 3 and t["all"]["total_tokens"] == 2350
    assert t["all"]["prompt_tokens_per_s"] == 2000.0  # the untimed request is left out of the rate


def test_runs_carry_their_token_counts(app_client, me, make_doc, db):
    now = datetime.now(UTC)
    job = _job(db, me, started_at=now - timedelta(hours=1), finished_at=now,
               result_json={"lines": 2})
    _chunk(db, me, make_doc(me, ["a"]), job_id=job.id, prompt_tokens=40, output_tokens=7)
    _chunk(db, me, None, job_id=job.id, ok=False, prompt_tokens=60, output_tokens=3)
    run = app_client.get("/stats/ollama").json()["runs"][0]
    assert (run["prompt_tokens"], run["output_tokens"]) == (100, 10)
