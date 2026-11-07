"""A single-slot request gate with interactive priority."""

from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass, field


@dataclass(order=True)
class _Waiter:
    sort_key: tuple[int, int]
    future: asyncio.Future[None] = field(compare=False)


class RequestGate:
    """Ensure only one request is in flight.

    Higher priorities overtake queued lower priorities, but never preempt an
    already running request. Equal priorities are FIFO.
    """

    def __init__(self) -> None:
        self._busy = False
        self._sequence = itertools.count()
        self._waiters: list[_Waiter] = []

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def waiting(self) -> int:
        return len(self._waiters)

    async def acquire(self, priority: int = 0) -> None:
        if not self._busy:
            self._busy = True
            return

        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        # heapq orders ascending, so negate the priority.
        waiter = _Waiter(sort_key=(-priority, next(self._sequence)), future=future)
        heapq.heappush(self._waiters, waiter)
        try:
            await future
        except asyncio.CancelledError:
            # The cancelled waiter is skipped when it reaches the front.
            raise

    def release(self) -> None:
        while self._waiters:
            waiter = heapq.heappop(self._waiters)
            if waiter.future.cancelled():
                continue
            waiter.future.set_result(None)
            return
        self._busy = False

    def fail_waiters(self, exception: BaseException) -> None:
        waiters = self._waiters
        self._waiters = []
        for waiter in waiters:
            if not waiter.future.done():
                waiter.future.set_exception(exception)
