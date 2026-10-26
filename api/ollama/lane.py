"""One lane per user: every request to a user's Ollama server goes through it, one at a time.

By-hand requests (priority) go before queued run chunks, but never cut the request in flight:
a chunk on a slow CPU is up to a minute of work that would be thrown away.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class _Lane:
    def __init__(self) -> None:
        self.held = False
        self.priority: deque[asyncio.Future[None]] = deque()
        self.normal: deque[asyncio.Future[None]] = deque()

    @property
    def idle(self) -> bool:
        return not self.held and not self.priority and not self.normal

    async def acquire(self, priority: bool) -> None:
        if not self.held and not self.priority and not self.normal:
            self.held = True
            return
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        queue = self.priority if priority else self.normal
        queue.append(fut)
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release()  # handed the lane just as we were cancelled: pass it on
            elif fut in queue:
                queue.remove(fut)
            raise

    def release(self) -> None:
        """Hand the lane straight to the next waiter (priority first), else free it."""
        for queue in (self.priority, self.normal):
            while queue:
                fut = queue.popleft()
                if not fut.done():
                    fut.set_result(None)
                    return
        self.held = False


class Lanes:
    """Per-user lanes, keyed by user id.

    # ponytail: in-process, so it keeps a by-hand stream and a run apart only when both live in
    # the same API process (like the job worker in api/jobs.py). The unique index stops two runs
    # per user, not a run in one process and a by-hand request in another. Swap for a per-user
    # Postgres advisory lock if the app ever runs several API processes.
    """

    def __init__(self) -> None:
        self._lanes: dict[int, _Lane] = {}

    @asynccontextmanager
    async def hold(self, user_id: int, *, priority: bool) -> AsyncIterator[None]:
        lane = self._lanes.setdefault(user_id, _Lane())
        try:
            await lane.acquire(priority)
        except asyncio.CancelledError:
            self._forget(user_id, lane)
            raise
        try:
            yield
        finally:
            lane.release()
            self._forget(user_id, lane)

    def waiting(self, user_id: int) -> bool:
        """A by-hand request is waiting for the lane."""
        lane = self._lanes.get(user_id)
        return lane is not None and any(not f.done() for f in lane.priority)

    def _forget(self, user_id: int, lane: _Lane) -> None:
        if lane.idle and self._lanes.get(user_id) is lane:
            del self._lanes[user_id]


LANES = Lanes()
