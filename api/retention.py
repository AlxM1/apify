"""Automatic data retention - cleans up old jobs and results."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select, func

from api.config import settings
from api.database import async_session
from api.models import ScrapeJob, ScrapeResult

logger = logging.getLogger(__name__)

_retention_task: asyncio.Task | None = None


async def cleanup_old_data():
    """Delete jobs and results older than retention_days."""
    cutoff = datetime.utcnow() - timedelta(days=settings.retention_days)

    async with async_session() as db:
        # Count what we're about to delete
        count = await db.scalar(
            select(func.count(ScrapeJob.id)).where(ScrapeJob.created_at < cutoff)
        ) or 0

        if count == 0:
            return

        # Delete results for old jobs
        old_job_ids = select(ScrapeJob.id).where(ScrapeJob.created_at < cutoff)
        await db.execute(
            delete(ScrapeResult).where(ScrapeResult.job_id.in_(old_job_ids))
        )

        # Delete old jobs
        await db.execute(delete(ScrapeJob).where(ScrapeJob.created_at < cutoff))
        await db.commit()

        logger.info(f"Retention: deleted {count} jobs older than {settings.retention_days} days")


async def retention_loop():
    """Run retention cleanup periodically."""
    logger.info(
        f"Retention cleanup enabled (keep={settings.retention_days}d, "
        f"interval={settings.retention_check_interval}s)"
    )
    while True:
        try:
            await cleanup_old_data()
        except Exception as e:
            logger.error(f"Retention cleanup error: {e}", exc_info=True)
        await asyncio.sleep(settings.retention_check_interval)


def start_retention():
    """Start the retention cleanup as a background task."""
    global _retention_task
    if not settings.retention_enabled:
        return
    _retention_task = asyncio.create_task(retention_loop())
    return _retention_task


def stop_retention():
    """Stop the retention cleanup."""
    global _retention_task
    if _retention_task and not _retention_task.done():
        _retention_task.cancel()
        _retention_task = None
