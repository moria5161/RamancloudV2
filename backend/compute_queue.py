"""FIFO admission for heavy work in the application's single worker process."""

import asyncio
import json
import logging
import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse


LOG = logging.getLogger(__name__)
_stream = ContextVar("compute_stream", default=None)
QUEUE_WAIT_SECONDS = 900


class ComputeQueueError(RuntimeError):
    pass


class ComputeCancelled(Exception):
    pass


class Ticket:
    def __init__(self, queue):
        self.queue = queue
        self.cancelled = False

    def acquire(self, cancelled=None, timeout=None, on_queued=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        q = self.queue
        with q.changed:
            last_position = None
            while True:
                if self.cancelled or (cancelled is not None and cancelled.is_set()):
                    raise ComputeCancelled()
                position = q.waiting.index(self) + int(q.active is not None)
                if position == 0:
                    q.waiting.popleft()
                    q.active = self
                    return
                if position != last_position and on_queued:
                    on_queued(position)
                    last_position = position
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise ComputeQueueError("等待计算超时，请重新提交。")
                q.changed.wait(.25 if cancelled is not None else remaining)

    def cancel_pending(self):
        q = self.queue
        with q.changed:
            if self in q.waiting:
                q.waiting.remove(self)
                self.cancelled = True
                q.changed.notify_all()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        q = self.queue
        with q.changed:
            if q.active is self:
                q.active = None
                q.changed.notify_all()
            else:
                self.cancel_pending()


class ComputeQueue:
    def __init__(self, capacity=8):
        self.capacity = capacity
        self.changed = threading.Condition()
        self.waiting = deque()
        self.active = None

    def reserve(self):
        with self.changed:
            if len(self.waiting) + int(self.active is not None) >= self.capacity:
                raise ComputeQueueError("计算队列已满，请稍后提交。")
            ticket = Ticket(self)
            self.waiting.append(ticket)
            return ticket


COMPUTE_QUEUE = ComputeQueue()


@contextmanager
def compute_slot():
    stream = _stream.get()

    def report_position(ahead):
        stream[0](type="status", message="排队中")
        stream[0](type="queued", ahead=ahead)

    with COMPUTE_QUEUE.reserve() as ticket:
        ticket.acquire(
            cancelled=stream[1] if stream else None,
            timeout=QUEUE_WAIT_SECONDS,
            on_queued=report_position if stream else None,
        )
        if stream:
            stream[0](type="status", message="运行中")
            stream[0](type="running")
        yield


def stream_cancelled():
    stream = _stream.get()
    return stream is not None and stream[1].is_set()


def stream_work(work, error_message):
    """Keep a request open while its work waits or runs, using bounded queue admission."""
    async def events():
        loop = asyncio.get_running_loop()
        outgoing = asyncio.Queue()
        cancelled = threading.Event()

        def emit(**item):
            if not cancelled.is_set():
                loop.call_soon_threadsafe(outgoing.put_nowait, item)

        def produce():
            context = _stream.set((emit, cancelled))
            try:
                if not cancelled.is_set():
                    result = work(emit)
                    if result is not None:
                        emit(type="result", data=result)
            except ComputeCancelled:
                pass
            except ComputeQueueError as exc:
                emit(type="error", message=str(exc), status=429)
            except HTTPException as exc:
                emit(type="error", message=exc.detail, status=exc.status_code)
            except Exception as exc:
                LOG.warning("Queued work failed: category=%s", type(exc).__name__)
                emit(type="error", message=error_message)
            finally:
                _stream.reset(context)
                loop.call_soon_threadsafe(outgoing.put_nowait, None)

        worker = asyncio.create_task(run_in_threadpool(produce))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(outgoing.get(), timeout=5)
                except asyncio.TimeoutError:
                    item = {"type": "heartbeat"}
                if item is None:
                    await worker
                    break
                yield json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n"
        finally:
            cancelled.set()

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
