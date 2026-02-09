"""Webhook and n8n integration endpoints."""

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth, create_access_token
from api.config import settings
from api.database import get_db
from api.models import ScrapeJob
from api.schemas import JobResponse, ScrapeRequest
from api.tasks import launch_job
from config.settings import PLATFORMS

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/scrape", response_model=JobResponse, status_code=201)
async def webhook_trigger_scrape(
    req: ScrapeRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    """Trigger a scrape via webhook (n8n HTTP Request node).

    Same as POST /api/scrapes but under /api/webhooks for clarity.
    Accepts the same ScrapeRequest payload.
    """
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

    launch_job(job.id)
    return job


@router.post("/n8n/trigger", status_code=201)
async def n8n_trigger(
    request: Request,
    x_webhook_secret: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Endpoint designed for n8n webhook triggers.

    Verifies the webhook secret if configured.
    Accepts a simplified payload: {platform, action, target, max_results?}
    """
    # Verify webhook secret if configured
    if settings.webhook_secret:
        body = await request.body()
        expected = hmac.new(
            settings.webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(x_webhook_secret or "", expected):
            raise HTTPException(403, "Invalid webhook signature")

    data = await request.json()

    platform = data.get("platform")
    action = data.get("action", "posts")
    target = data.get("target")
    max_results = data.get("max_results", settings.default_max_results)

    if not platform or not target:
        raise HTTPException(400, "platform and target are required")
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {platform}")

    job = ScrapeJob(
        platform=platform,
        action=action,
        target=target,
        max_results=max_results,
        config=data.get("config", {}),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    launch_job(job.id)

    return {
        "ok": True,
        "job_id": job.id,
        "status": "pending",
        "message": f"Scrape job launched: {platform}/{action}/{target}",
    }


@router.post("/token")
async def generate_token(_auth: str = Depends(require_auth)):
    """Generate a JWT token for API access.

    Requires valid API key to generate token.
    Useful for n8n HTTP Header Auth.
    """
    token = create_access_token({"sub": "api_user", "type": "webhook"})
    return {"access_token": token, "token_type": "bearer"}
