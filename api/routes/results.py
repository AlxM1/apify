"""Global results query endpoints."""

import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import ScrapeResult

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("")
async def search_results(
    platform: str | None = None,
    content_type: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Search across all scraped results."""
    query = select(ScrapeResult).order_by(desc(ScrapeResult.scraped_at))

    if platform:
        query = query.where(ScrapeResult.platform == platform)
    if content_type:
        query = query.where(ScrapeResult.content_type == content_type)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()

    # If text search query provided, filter in Python (SQLite JSON search is limited)
    if q:
        q_lower = q.lower()
        rows = [
            r for r in rows
            if q_lower in json.dumps(r.data).lower()
        ]

    return [
        {
            "id": r.id,
            "job_id": r.job_id,
            "platform": r.platform,
            "content_type": r.content_type,
            "data": r.data,
            "url": r.url,
            "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
        }
        for r in rows
    ]


@router.get("/export")
async def export_results(
    job_id: int | None = None,
    platform: str | None = None,
    format: str = Query(default="json", pattern="^(json|jsonl|csv)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export results as JSON, JSONL, or CSV."""
    query = select(ScrapeResult).order_by(ScrapeResult.id)
    if job_id:
        query = query.where(ScrapeResult.job_id == job_id)
    if platform:
        query = query.where(ScrapeResult.platform == platform)

    result = await db.execute(query)
    rows = result.scalars().all()

    items = [
        {
            "platform": r.platform,
            "content_type": r.content_type,
            "url": r.url,
            "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            **r.data,
        }
        for r in rows
    ]

    if format == "jsonl":
        output = "\n".join(json.dumps(item) for item in items)
        return StreamingResponse(
            io.BytesIO(output.encode()),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=results.jsonl"},
        )
    elif format == "csv":
        import pandas as pd

        df = pd.json_normalize(items)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=results.csv"},
        )
    else:
        return StreamingResponse(
            io.BytesIO(json.dumps(items, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=results.json"},
        )


@router.get("/stats")
async def result_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregate stats across all results."""
    total = await db.scalar(select(func.count(ScrapeResult.id)))

    # Per-platform counts
    q = (
        select(ScrapeResult.platform, func.count(ScrapeResult.id))
        .group_by(ScrapeResult.platform)
        .order_by(desc(func.count(ScrapeResult.id)))
    )
    result = await db.execute(q)
    by_platform = {row[0]: row[1] for row in result.all()}

    # Per-type counts
    q2 = (
        select(ScrapeResult.content_type, func.count(ScrapeResult.id))
        .group_by(ScrapeResult.content_type)
    )
    result2 = await db.execute(q2)
    by_type = {row[0]: row[1] for row in result2.all()}

    return {
        "total_results": total or 0,
        "by_platform": by_platform,
        "by_content_type": by_type,
    }
