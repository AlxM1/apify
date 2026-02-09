"""Background task runner for scrape jobs."""

import asyncio
import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy import select

from api.database import async_session
from api.models import JobStatus, ScrapeJob, ScrapeResult
from config.settings import get_scraper_class
from scrapers.base import ScraperConfig

logger = logging.getLogger(__name__)

# In-memory tracker for running jobs (job_id -> asyncio.Task)
_running_tasks: dict[int, asyncio.Task] = {}


async def run_scrape_job(job_id: int) -> None:
    """Execute a scrape job in the background."""
    async with async_session() as db:
        job = await db.get(ScrapeJob, job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.commit()

    scraper = None
    try:
        config = ScraperConfig(
            max_results=job.max_results,
            proxy=job.config.get("proxy") if job.config else None,
            delay_between_requests=job.config.get("delay", 1.0) if job.config else 1.0,
            headless=job.config.get("headless", True) if job.config else True,
        )

        scraper_cls = get_scraper_class(job.platform)
        scraper = scraper_cls(config)

        # Execute the scrape action
        if job.action == "profile":
            results = await scraper.scrape_profile(job.target)
        elif job.action == "posts":
            results = await scraper.scrape_posts(job.target, max_results=job.max_results)
        elif job.action == "search":
            results = await scraper.search(job.target, max_results=job.max_results)
        else:
            raise ValueError(f"Unknown action: {job.action}")

        # Store results in DB
        async with async_session() as db:
            job = await db.get(ScrapeJob, job_id)
            for r in results:
                db_result = ScrapeResult(
                    job_id=job_id,
                    platform=r.platform,
                    content_type=r.content_type,
                    data=r.data,
                    url=r.url,
                    scraped_at=datetime.fromisoformat(r.scraped_at),
                )
                db.add(db_result)

            now = datetime.utcnow()
            job.status = JobStatus.COMPLETED
            job.completed_at = now
            job.result_count = len(results)
            if job.started_at:
                job.duration_seconds = (now - job.started_at).total_seconds()
            await db.commit()

        logger.info(f"Job {job_id} completed: {len(results)} results")

    except asyncio.CancelledError:
        async with async_session() as db:
            job = await db.get(ScrapeJob, job_id)
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            await db.commit()
        logger.info(f"Job {job_id} cancelled")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        async with async_session() as db:
            job = await db.get(ScrapeJob, job_id)
            now = datetime.utcnow()
            job.status = JobStatus.FAILED
            job.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            job.completed_at = now
            if job.started_at:
                job.duration_seconds = (now - job.started_at).total_seconds()
            await db.commit()

    finally:
        if scraper:
            await scraper.close()
        _running_tasks.pop(job_id, None)


def launch_job(job_id: int) -> asyncio.Task:
    """Launch a scrape job as a background asyncio task."""
    task = asyncio.create_task(run_scrape_job(job_id))
    _running_tasks[job_id] = task
    return task


def cancel_job(job_id: int) -> bool:
    """Cancel a running job. Returns True if cancelled."""
    task = _running_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


def get_running_job_ids() -> list[int]:
    """Return list of currently running job IDs."""
    return [jid for jid, t in _running_tasks.items() if not t.done()]
