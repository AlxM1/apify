"""Scrape job CRUD endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import require_auth
from api.database import get_db
from api.models import JobStatus, ScrapeJob, ScrapeResult
from api.schemas import (
    JobDetailResponse,
    JobResponse,
    ResultResponse,
    ScrapeRequest,
)
from api.tasks import cancel_job, launch_job
from config.settings import PLATFORMS

router = APIRouter(prefix="/api/scrapes", tags=["scrapes"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_scrape(req: ScrapeRequest, db: AsyncSession = Depends(get_db), _auth: str = Depends(require_auth)):
    """Launch a new scrape job."""
    if req.platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {req.platform}")

    job = ScrapeJob(
        platform=req.platform,
        action=req.action,
        target=req.target,
        max_results=req.max_results,
        config={
            "proxy": req.proxy,
            "delay": req.delay,
            "headless": req.headless,
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    launch_job(job.id)

    return job


@router.get("", response_model=list[JobResponse])
async def list_scrapes(
    platform: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List scrape jobs with optional filtering."""
    query = select(ScrapeJob).order_by(desc(ScrapeJob.created_at))

    if platform:
        query = query.where(ScrapeJob.platform == platform)
    if status:
        query = query.where(ScrapeJob.status == status)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_scrape(job_id: int, db: AsyncSession = Depends(get_db)):
    """Get a scrape job with its results."""
    query = (
        select(ScrapeJob)
        .where(ScrapeJob.id == job_id)
        .options(selectinload(ScrapeJob.results))
    )
    result = await db.execute(query)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.delete("/{job_id}")
async def delete_scrape(job_id: int, db: AsyncSession = Depends(get_db), _auth: str = Depends(require_auth)):
    """Delete a scrape job and its results."""
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Cancel if running
    cancel_job(job_id)

    await db.delete(job)
    await db.commit()
    return {"ok": True, "deleted": job_id}


@router.post("/{job_id}/cancel")
async def cancel_scrape(job_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a running scrape job."""
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(400, f"Cannot cancel job with status: {job.status.value}")

    cancelled = cancel_job(job_id)
    if not cancelled:
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        await db.commit()

    return {"ok": True, "job_id": job_id, "status": "cancelled"}


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=201)
async def retry_scrape(job_id: int, db: AsyncSession = Depends(get_db)):
    """Retry a failed scrape job by creating a new one with the same config."""
    old = await db.get(ScrapeJob, job_id)
    if not old:
        raise HTTPException(404, "Job not found")

    job = ScrapeJob(
        platform=old.platform,
        action=old.action,
        target=old.target,
        max_results=old.max_results,
        config=old.config,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    launch_job(job.id)
    return job


@router.get("/{job_id}/results", response_model=list[ResultResponse])
async def get_scrape_results(
    job_id: int,
    content_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get results for a specific scrape job."""
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    query = (
        select(ScrapeResult)
        .where(ScrapeResult.job_id == job_id)
        .order_by(ScrapeResult.id)
    )
    if content_type:
        query = query.where(ScrapeResult.content_type == content_type)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
