"""The live log of an Ollama run: what the runner is doing, kept in memory per job.

# ponytail: in-process, like the lane (api/ollama/lane.py): the route that reads a log must live
# in the process that runs the job. Nothing reaches the database, so a restart starts every log
# empty; the chunk rows (ollama_chunks) stay the lasting record of what was asked.
"""

from __future__ import annotations

import threading
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from api.ollama.translate import ChunkResult

MAX_ENTRIES = 500  # per run; older entries drop off the top
MAX_RUNS = 50  # logs kept server-wide; the oldest is forgotten first


@dataclass(frozen=True)
class Entry:
    seq: int
    at: datetime
    level: str  # info / warn / error
    text: str


@dataclass
class _Log:
    entries: deque[Entry] = field(default_factory=lambda: deque(maxlen=MAX_ENTRIES))
    seq: int = 0
    now: str | None = None  # what the run is doing this moment; None between steps
    ended: bool = False


_LOGS: OrderedDict[int, _Log] = OrderedDict()
_lock = threading.Lock()  # the runner writes on the event loop, the route reads in the threadpool


def _get(job_id: int) -> _Log:
    log = _LOGS.get(job_id)
    if log is None:
        log = _LOGS[job_id] = _Log()
        while len(_LOGS) > MAX_RUNS:
            _LOGS.popitem(last=False)
    return log


def add(job_id: int, text: str, level: str = "info") -> None:
    with _lock:
        log = _get(job_id)
        log.seq += 1
        log.entries.append(Entry(log.seq, datetime.now(UTC), level, text))
        log.now = None


def doing(job_id: int, text: str | None) -> None:
    """Set (or clear) the one-line "now" status, which is replaced, not appended."""
    with _lock:
        _get(job_id).now = text


def end(job_id: int, text: str, level: str = "info") -> None:
    add(job_id, text, level)
    with _lock:
        _LOGS[job_id].ended = True


@dataclass(frozen=True)
class Snapshot:
    entries: list[Entry]
    now: str | None
    ended: bool
    next: int  # pass back as `after` for the entries after these


def read(job_id: int, after: int = 0) -> Snapshot | None:
    """The entries after `after`, or None when this process holds no log for the job."""
    with _lock:
        log = _LOGS.get(job_id)
        if log is None:
            return None
        return Snapshot([e for e in log.entries if e.seq > after], log.now, log.ended, log.seq)


def lines(n: int) -> str:
    return f"{n:,} {'line' if n == 1 else 'lines'}"


def duration(ms: float) -> str:
    s = round(ms / 1000)
    return f"{s} s" if s < 120 else f"{s // 60} min {s % 60} s"


def _rejected(result: ChunkResult) -> str:
    """The distinct reasons check() rejected an answer, most frequent first (at most three)."""
    counts = Counter(r.error for r in result.requests if r.error)
    return "; ".join(f"{why}" + (f" ×{n}" if n > 1 else "")
                     for why, n in counts.most_common(3))


def answered(result: ChunkResult, asked: int) -> str:
    """The entry for a saved chunk: how much came back, how long it took, and why an answer
    was rejected when one was."""
    parts = [f"Got {len(result.lines):,} of {lines(asked)}"]
    if result.failed:
        parts.append(f"{len(result.failed):,} failed")
    took = sum(r.total_ms or 0 for r in result.requests)
    if took:
        parts.append(f"in {duration(took)}")
    tokens = sum(r.output_tokens or 0 for r in result.requests)
    eval_ms = sum(r.eval_ms or 0 for r in result.requests)
    if tokens and eval_ms:
        parts.append(f"{tokens / eval_ms * 1000:.1f} tokens/s")
    if len(result.requests) > 1:
        parts.append(f"split into {len(result.requests)} requests")
    rejected = _rejected(result)
    if rejected:
        parts.append(f"an answer did not check out: {rejected}")
    return ", ".join(parts)


_ENDINGS = {
    "finished": "Finished: nothing is left in the queue",
    "window closed": "Stopped: the night window closed",
    "cancelled": "Stopped: cancelled",
}


def ending(state: str, message: str, reason: str, done: int, chunks: int, failed: int) -> str:
    counts = f"{lines(done)} translated in {chunks:,} {'chunk' if chunks == 1 else 'chunks'}"
    if failed:
        counts += f", {failed:,} failed"
    if state == "failed":
        return f"Failed: {message or 'the run stopped'} ({counts})"
    return f"{_ENDINGS.get(reason, reason)} ({counts})"


def clear() -> None:
    """Forget every log (tests)."""
    with _lock:
        _LOGS.clear()
