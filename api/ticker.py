"""The once-a-minute loop: the Ollama night runs (api/ollama/schedule.py) and the nightly
syosetu check (api/syosetu_nightly.py). Each tick has its own session and its own try, so
one failing never skips the other. Single process only, like the job worker."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from api import syosetu_nightly
from api.backup import state
from api.db import SessionLocal
from api.ollama import schedule

log = logging.getLogger(__name__)
TICKS = (("ollama schedule", schedule), ("syosetu nightly", syosetu_nightly))


def _tick_once() -> None:
    try:
        with state.work():
            now = datetime.now(UTC)
            for name, module in TICKS:
                with SessionLocal() as db:
                    try:
                        module.tick(db, now)
                    except Exception:
                        log.exception("%s tick failed", name)
    except state.Maintenance:
        pass  # a restore is running: this tick is skipped, the next one is a minute away


async def ticker(stop: asyncio.Event, every: float = 60.0) -> None:
    """Run the ticks every ``every`` seconds until ``stop`` is set."""
    while not stop.is_set():
        try:
            await run_in_threadpool(_tick_once)
        except Exception:
            log.exception("tick failed")
        try:
            await asyncio.wait_for(stop.wait(), every)
        except TimeoutError:
            pass
