"""Scheduled job CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.database import get_db
from api.models import ScheduledJob
from api.schemas import ScheduleRequest, ScheduleResponse, ScheduleUpdate
from api.scheduler import compute_next_run
from config.settings import PLATFORMS

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    req: ScheduleRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Create a new scheduled recurring scrape."""
    if req.platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {req.platform}")

    # Validate cron expression
    try:
        next_run = compute_next_run(req.cron_expression)
    except (ValueError, KeyError):
        raise HTTPException(400, f"Invalid cron expression: {req.cron_expression}")

    sj = ScheduledJob(
        name=req.name,
        platform=req.platform,
        action=req.action,
        target=req.target,
        max_results=req.max_results,
        config=req.config,
        cron_expression=req.cron_expression,
        next_run=next_run,
    )
    db.add(sj)
    await db.commit()
    await db.refresh(sj)
    return sj


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """List all scheduled jobs."""
    result = await db.execute(
        select(ScheduledJob).order_by(desc(ScheduledJob.created_at)).limit(limit)
    )
    return result.scalars().all()


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Get a specific scheduled job."""
    sj = await db.get(ScheduledJob, schedule_id)
    if not sj:
        raise HTTPException(404, "Schedule not found")
    return sj


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    req: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Update a scheduled job."""
    sj = await db.get(ScheduledJob, schedule_id)
    if not sj:
        raise HTTPException(404, "Schedule not found")

    if req.name is not None:
        sj.name = req.name
    if req.cron_expression is not None:
        try:
            sj.cron_expression = req.cron_expression
            sj.next_run = compute_next_run(req.cron_expression)
        except (ValueError, KeyError):
            raise HTTPException(400, f"Invalid cron expression: {req.cron_expression}")
    if req.enabled is not None:
        sj.enabled = int(req.enabled)
    if req.max_results is not None:
        sj.max_results = req.max_results
    if req.config is not None:
        sj.config = req.config

    await db.commit()
    await db.refresh(sj)
    return sj


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Delete a scheduled job."""
    sj = await db.get(ScheduledJob, schedule_id)
    if not sj:
        raise HTTPException(404, "Schedule not found")
    await db.delete(sj)
    await db.commit()
    return {"ok": True, "deleted": schedule_id}
