"""Webhook notifications for job events."""

import hashlib
import hmac
import json
import logging
from datetime import datetime

import httpx

from api.config import settings

logger = logging.getLogger(__name__)


async def notify_job_complete(job_data: dict):
    """Send a webhook notification when a job completes or fails.

    Payload is signed with HMAC-SHA256 if webhook_secret is configured.
    Compatible with n8n webhook nodes.
    """
    url = settings.webhook_url
    if not url:
        return

    payload = {
        "event": "job.completed" if job_data.get("status") == "completed" else "job.failed",
        "timestamp": datetime.utcnow().isoformat(),
        "job": job_data,
    }

    body = json.dumps(payload)
    headers = {"Content-Type": "application/json"}

    # Sign payload if secret is configured
    if settings.webhook_secret:
        signature = hmac.new(
            settings.webhook_secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=body, headers=headers)
            logger.info(f"Webhook sent to {url}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")
