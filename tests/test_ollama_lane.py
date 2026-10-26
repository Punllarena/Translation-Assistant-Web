import asyncio

from api.ollama.lane import Lanes


async def _take(lanes, user, priority, order, name, release: asyncio.Event | None = None):
    async with lanes.hold(user, priority=priority):
        order.append(name)
        if release is not None:
            await release.wait()


async def test_priority_waiter_goes_before_queued_run_chunk():
    lanes, order, release = Lanes(), [], asyncio.Event()
    holder = asyncio.create_task(_take(lanes, 1, False, order, "chunk 1", release))
    await asyncio.sleep(0)
    run = asyncio.create_task(_take(lanes, 1, False, order, "chunk 2"))
    await asyncio.sleep(0)
    assert lanes.waiting(1) is False
    by_hand = asyncio.create_task(_take(lanes, 1, True, order, "by hand"))
    await asyncio.sleep(0)
    assert order == ["chunk 1"] and lanes.waiting(1) is True  # the current chunk is never cut
    release.set()
    await asyncio.gather(holder, run, by_hand)
    assert order == ["chunk 1", "by hand", "chunk 2"]
    assert lanes.waiting(1) is False and lanes._lanes == {}


async def test_users_do_not_share_a_lane():
    lanes, order, release = Lanes(), [], asyncio.Event()
    a = asyncio.create_task(_take(lanes, 1, False, order, "a", release))
    await asyncio.sleep(0)
    await asyncio.wait_for(_take(lanes, 2, False, order, "b"), 1)
    assert order == ["a", "b"]
    release.set()
    await a


async def test_a_cancelled_waiter_leaves_the_queue():
    lanes, order, release = Lanes(), [], asyncio.Event()
    holder = asyncio.create_task(_take(lanes, 1, False, order, "first", release))
    await asyncio.sleep(0)
    gone = asyncio.create_task(_take(lanes, 1, True, order, "gone"))
    await asyncio.sleep(0)
    gone.cancel()
    await asyncio.gather(gone, return_exceptions=True)
    assert lanes.waiting(1) is False
    release.set()
    await holder
    await asyncio.wait_for(_take(lanes, 1, False, order, "next"), 1)
    assert order == ["first", "next"]


async def test_wait_reason_names_the_holder():
    lanes, order = Lanes(), []
    assert lanes.wait_reason(1) is None
    release = asyncio.Event()
    run = asyncio.create_task(_take(lanes, 1, False, order, "run", release))
    await asyncio.sleep(0)
    assert lanes.wait_reason(1) == "run" and lanes.busy(1)
    by_hand = asyncio.create_task(_take(lanes, 1, True, order, "by hand", release))
    await asyncio.sleep(0)
    assert lanes.wait_reason(1) == "manual"  # a by-hand request is queued ahead
    release.set()
    await asyncio.gather(run, by_hand)
    assert lanes.wait_reason(1) is None
    release = asyncio.Event()
    holder = asyncio.create_task(_take(lanes, 1, True, order, "by hand 2", release))
    await asyncio.sleep(0)
    assert lanes.wait_reason(1) == "manual"
    release.set()
    await holder
