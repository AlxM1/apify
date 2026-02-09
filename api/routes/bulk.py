"""Bulk operations - batch scrapes and deduplication."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.database import get_db
from api.models import ScrapeJob, ScrapeResult
from api.schemas import JobResponse
from api.tasks import launch_job
from config.settings import PLATFORMS

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


class BulkTarget(BaseModel):
    platform: str
    action: str = "posts"
    target: str
    max_results: int = 100


class BulkRequest(BaseModel):
    targets: list[BulkTarget] = Field(min_length=1, max_length=100)
    proxy: str | None = None
    delay: float = 1.0
    headless: bool = True


@router.post("/scrape", status_code=201)
async def bulk_scrape(
    req: BulkRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Launch multiple scrape jobs at once.

    Accepts up to 100 targets. Each creates a separate job that runs
    in the background. Returns the list of created job IDs.
    """
    jobs = []
    errors = []

    for i, t in enumerate(req.targets):
        if t.platform not in PLATFORMS:
            errors.append({"index": i, "error": f"Unknown platform: {t.platform}"})
            continue

        job = ScrapeJob(
            platform=t.platform,
            action=t.action,
            target=t.target,
            max_results=t.max_results,
            config={
                "proxy": req.proxy,
                "delay": req.delay,
                "headless": req.headless,
            },
        )
        db.add(job)
        await db.flush()
        jobs.append(job)

    await db.commit()

    # Launch all jobs
    for job in jobs:
        await db.refresh(job)
        launch_job(job.id)

    return {
        "ok": True,
        "launched": len(jobs),
        "errors": errors,
        "job_ids": [j.id for j in jobs],
    }


@router.post("/deduplicate")
async def deduplicate_results(
    platform: str | None = None,
    dry_run: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Find and remove duplicate results.

    Duplicates are detected by matching (platform, content_type, url).
    Keeps the earliest result and removes later duplicates.

    Set dry_run=false to actually delete.
    """
    # Find duplicates: same platform + content_type + url
    base = (
        select(
            ScrapeResult.platform,
            ScrapeResult.content_type,
            ScrapeResult.url,
            func.count(ScrapeResult.id).label("cnt"),
            func.min(ScrapeResult.id).label("keep_id"),
        )
        .where(ScrapeResult.url.isnot(None))
        .group_by(ScrapeResult.platform, ScrapeResult.content_type, ScrapeResult.url)
        .having(func.count(ScrapeResult.id) > 1)
    )

    if platform:
        base = base.where(ScrapeResult.platform == platform)

    result = await db.execute(base)
    dupes = result.all()

    total_dupes = sum(row.cnt - 1 for row in dupes)

    if dry_run or total_dupes == 0:
        return {
            "dry_run": dry_run,
            "duplicate_groups": len(dupes),
            "total_duplicates": total_dupes,
            "would_delete": total_dupes,
        }

    # Actually delete duplicates (keep the earliest ID in each group)
    deleted = 0
    for row in dupes:
        del_q = (
            delete(ScrapeResult)
            .where(
                ScrapeResult.platform == row.platform,
                ScrapeResult.content_type == row.content_type,
                ScrapeResult.url == row.url,
                ScrapeResult.id != row.keep_id,
            )
        )
        r = await db.execute(del_q)
        deleted += r.rowcount

    await db.commit()

    # Update result counts on affected jobs
    job_ids_q = select(func.distinct(ScrapeResult.job_id))
    job_ids_result = await db.execute(job_ids_q)
    for (jid,) in job_ids_result.all():
        count = await db.scalar(
            select(func.count(ScrapeResult.id)).where(ScrapeResult.job_id == jid)
        )
        job = await db.get(ScrapeJob, jid)
        if job:
            job.result_count = count or 0
    await db.commit()

    return {
        "dry_run": False,
        "duplicate_groups": len(dupes),
        "deleted": deleted,
    }
