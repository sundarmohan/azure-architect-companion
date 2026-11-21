import asyncio
import contextlib

from app.db.session import SessionLocal

from .connection_service import MonitoringConnectionService

_task: asyncio.Task | None = None


async def _run() -> None:
    service = MonitoringConnectionService()
    while True:
        await asyncio.sleep(service.interval)
        async with SessionLocal() as db:
            await service.refresh_all(db)


def start_monitoring_worker() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run(), name="monitoring-refresh-worker")


async def stop_monitoring_worker() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None
