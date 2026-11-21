import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from .observation_models import AzureObservationSchedule
from .observations import KINDS, refresh_observations

logger = logging.getLogger(__name__)


async def claim_due_schedule():
    async with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        schedule = await db.scalar(select(AzureObservationSchedule).where(
            AzureObservationSchedule.enabled.is_(True), AzureObservationSchedule.next_run_at <= now
        ).order_by(AzureObservationSchedule.next_run_at).limit(1).with_for_update(skip_locked=True))
        if schedule is None:
            return None
        selected = (schedule.client_id, schedule.subscription_id, schedule.generation, schedule.include_security)
        schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
        await db.commit()
        return selected


async def run_worker():
    # Allow startup and immediate user requests to finish before scheduled work.
    await asyncio.sleep(10)
    while True:
        try:
            selected = await claim_due_schedule()
            if selected:
                async with SessionLocal() as db:
                    client_id, subscription_id, generation, include_security = selected
                    kinds = (*KINDS, "security") if include_security else KINDS
                    await refresh_observations(db, client_id, subscription_id, kinds, schedule_generation=generation)
        except Exception as error:
            # Provider credentials and remote response bodies are outside worker logs.
            logger.warning("Scheduled Azure observation failed (%s)", type(error).__name__)
        await asyncio.sleep(10)


async def stop_worker(task):
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
