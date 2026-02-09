"""Cron-based job scheduler for recurring scrapes."""

import asyncio
import logging
from datetime import datetime

from croniter import croniter
from sqlalchemy import select

from api.config import settings
from api.database import async_session
from api.models import JobStatus, ScheduledJob, ScrapeJob
from api.tasks import launch_job

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


def compute_next_run(cron_expr: str, base: datetime | None = None) -> datetime:
    """Compute the next run time from a cron expression."""
    base = base or datetime.utcnow()
    cron = croniter(cron_expr, base)
    return cron.get_next(datetime)


async def _check_and_run():
    """Check all enabled scheduled jobs and launch any that are due."""
    now = datetime.utcnow()

    async with async_session() as db:
        query = select(ScheduledJob).where(
            ScheduledJob.enabled == 1,
            ScheduledJob.next_run <= now,
        )
        result = await db.execute(query)
        due_jobs = result.scalars().all()

        for sj in due_jobs:
            logger.info(f"Scheduler: launching '{sj.name}' ({sj.platform}/{sj.action}/{sj.target})")

            # Create a new ScrapeJob
            job = ScrapeJob(
                platform=sj.platform,
                action=sj.action,
                target=sj.target,
                max_results=sj.max_results,
                config=sj.config or {},
            )
            db.add(job)
            await db.flush()  # get the ID

            # Update scheduled job timing
            sj.last_run = now
            sj.next_run = compute_next_run(sj.cron_expression, now)

            await db.commit()

            # Launch the actual scrape
            launch_job(job.id)

        if due_jobs:
            logger.info(f"Scheduler: launched {len(due_jobs)} job(s)")


async def scheduler_loop():
    """Main scheduler loop - runs forever, checking periodically."""
    logger.info(
        f"Scheduler started (interval={settings.scheduler_check_interval}s)"
    )
    while True:
        try:
            await _check_and_run()
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
        await asyncio.sleep(settings.scheduler_check_interval)


def start_scheduler():
    """Start the scheduler as a background task."""
    global _scheduler_task
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via config")
        return
    _scheduler_task = asyncio.create_task(scheduler_loop())
    return _scheduler_task


def stop_scheduler():
    """Stop the scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
