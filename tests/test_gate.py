from __future__ import annotations

import asyncio

import pytest

from aiosmartfriends.gate import RequestGate


@pytest.mark.asyncio
async def test_gate_is_exclusive() -> None:
    gate = RequestGate()
    order: list[str] = []

    async def worker(name: str) -> None:
        await gate.acquire()
        order.append(f"{name}-start")
        await asyncio.sleep(0.01)
        order.append(f"{name}-end")
        gate.release()

    await asyncio.gather(worker("a"), worker("b"))
    assert order in (
        ["a-start", "a-end", "b-start", "b-end"],
        ["b-start", "b-end", "a-start", "a-end"],
    )


@pytest.mark.asyncio
async def test_interactive_priority_overtakes_queued_poll() -> None:
    gate = RequestGate()
    await gate.acquire()
    order: list[str] = []

    async def waiter(name: str, priority: int) -> None:
        await gate.acquire(priority)
        order.append(name)
        gate.release()

    poll = asyncio.create_task(waiter("poll", 0))
    await asyncio.sleep(0)
    command = asyncio.create_task(waiter("command", 10))
    await asyncio.sleep(0)
    gate.release()
    await asyncio.gather(poll, command)
    assert order[0] == "command"


@pytest.mark.asyncio
async def test_cancelled_waiter_is_skipped() -> None:
    gate = RequestGate()
    await gate.acquire()
    started = asyncio.Event()

    async def waiter() -> None:
        await gate.acquire()
        started.set()
        gate.release()

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    gate.release()
    assert not gate.busy

    await gate.acquire()
    gate.release()
