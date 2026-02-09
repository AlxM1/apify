"""Dashboard stats endpoint."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import JobStatus, ScrapeJob, ScrapeResult
from api.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard overview statistics."""
    total = await db.scalar(select(func.count(ScrapeJob.id))) or 0
    completed = (
        await db.scalar(
            select(func.count(ScrapeJob.id)).where(
                ScrapeJob.status == JobStatus.COMPLETED
            )
        )
        or 0
    )
    failed = (
        await db.scalar(
            select(func.count(ScrapeJob.id)).where(
                ScrapeJob.status == JobStatus.FAILED
            )
        )
        or 0
    )
    running = (
        await db.scalar(
            select(func.count(ScrapeJob.id)).where(
                ScrapeJob.status == JobStatus.RUNNING
            )
        )
        or 0
    )
    pending = (
        await db.scalar(
            select(func.count(ScrapeJob.id)).where(
                ScrapeJob.status == JobStatus.PENDING
            )
        )
        or 0
    )
    total_results = await db.scalar(select(func.count(ScrapeResult.id))) or 0

    # Results scraped today
    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    results_today = (
        await db.scalar(
            select(func.count(ScrapeResult.id)).where(
                ScrapeResult.scraped_at >= today_start
            )
        )
        or 0
    )

    # Distinct platforms used
    q = select(func.count(func.distinct(ScrapeJob.platform)))
    platforms_used = await db.scalar(q) or 0

    # Average duration of completed jobs
    avg_dur = await db.scalar(
        select(func.avg(ScrapeJob.duration_seconds)).where(
            ScrapeJob.status == JobStatus.COMPLETED,
            ScrapeJob.duration_seconds.isnot(None),
        )
    )

    return DashboardStats(
        total_jobs=total,
        completed_jobs=completed,
        failed_jobs=failed,
        running_jobs=running,
        pending_jobs=pending,
        total_results=total_results,
        results_today=results_today,
        platforms_used=platforms_used,
        avg_duration=round(avg_dur, 2) if avg_dur else None,
    )
