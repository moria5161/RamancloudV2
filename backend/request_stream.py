"""Stream status and results for long-lived HTTP requests."""

import asyncio
import json
import logging
import threading
from contextvars import ContextVar

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse


LOG = logging.getLogger(__name__)
_cancelled = ContextVar("stream_cancelled", default=None)


class RequestCancelled(Exception):
    pass


def stream_cancelled():
    event = _cancelled.get()
    return event is not None and event.is_set()


def stream_work(work, error_message):
    """Keep the connection open while the request runs in a worker thread."""
    async def events():
        loop = asyncio.get_running_loop()
        outgoing = asyncio.Queue()
        cancelled = threading.Event()

        def emit(**item):
            if not cancelled.is_set():
                loop.call_soon_threadsafe(outgoing.put_nowait, item)

        def produce():
            context = _cancelled.set(cancelled)
            try:
                if not cancelled.is_set():
                    emit(type="running")
                    result = work(emit)
                    if result is not None:
                        emit(type="result", data=result)
            except RequestCancelled:
                pass
            except HTTPException as exc:
                emit(type="error", message=exc.detail, status=exc.status_code)
            except Exception as exc:
                LOG.warning("Streamed request failed: category=%s", type(exc).__name__)
                emit(type="error", message=error_message)
            finally:
                _cancelled.reset(context)
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
