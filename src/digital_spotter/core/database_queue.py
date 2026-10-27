"""Bounded off-loop execution for SQLite repository operations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast


ResultT = TypeVar("ResultT")


class DatabaseQueueError(RuntimeError):
    """Base failure for the bounded database worker."""


class DatabaseQueueFull(DatabaseQueueError):
    """Raised instead of blocking when the database queue has no capacity."""


class DatabaseQueueClosed(DatabaseQueueError):
    """Raised when work is submitted after shutdown begins."""


@dataclass
class _WorkItem(Generic[ResultT]):
    operation: Callable[[], ResultT]
    future: asyncio.Future[ResultT]


_STOP = object()


class DatabaseWorkQueue:
    """Run blocking repository calls in one worker with explicit backpressure."""

    def __init__(self, *, max_items: int = 256) -> None:
        if not 1 <= max_items <= 4096:
            raise ValueError("database queue size must be between 1 and 4096")
        self.max_items = max_items
        self._queue: asyncio.Queue[_WorkItem[object] | object] = asyncio.Queue(
            maxsize=max_items
        )
        self._worker: asyncio.Task[None] | None = None
        self._closed = False
        self.submitted = 0
        self.completed = 0
        self.failed = 0
        self.rejected_full = 0

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._closed:
            raise DatabaseQueueClosed("database queue is closed")
        if self._worker is None:
            self._worker = asyncio.create_task(
                self._run(),
                name="digital-spotter-database-writer",
            )

    async def submit(self, operation: Callable[[], ResultT]) -> ResultT:
        if self._closed:
            raise DatabaseQueueClosed("database queue is closed")
        await self.start()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ResultT] = loop.create_future()
        item = _WorkItem(operation=operation, future=future)
        try:
            self._queue.put_nowait(cast(_WorkItem[object], item))
        except asyncio.QueueFull as exc:
            self.rejected_full += 1
            raise DatabaseQueueFull(
                f"database work queue reached its {self.max_items}-item limit"
            ) from exc
        self.submitted += 1
        return await future

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is _STOP:
                    return
                work = cast(_WorkItem[object], item)
                try:
                    result = await asyncio.to_thread(work.operation)
                except Exception as exc:
                    self.failed += 1
                    if not work.future.done():
                        work.future.set_exception(exc)
                else:
                    self.completed += 1
                    if not work.future.done():
                        work.future.set_result(result)
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._worker is None:
            return
        await self._queue.join()
        await self._queue.put(_STOP)
        await self._worker
        self._worker = None
