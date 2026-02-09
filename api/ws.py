"""WebSocket manager for real-time job updates."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.database import async_session
from api.models import ScrapeJob

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts job updates."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WS connected ({len(self.active)} total)")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info(f"WS disconnected ({len(self.active)} total)")

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        if not self.active:
            return
        data = json.dumps(message, default=str)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

    async def broadcast_job_update(self, job_id: int):
        """Fetch job from DB and broadcast its current state."""
        async with async_session() as db:
            job = await db.get(ScrapeJob, job_id)
            if not job:
                return
            await self.broadcast({
                "type": "job_update",
                "job": {
                    "id": job.id,
                    "platform": job.platform,
                    "action": job.action,
                    "target": job.target,
                    "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
                    "result_count": job.result_count,
                    "error": job.error,
                    "duration_seconds": job.duration_seconds,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                },
            })


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket):
    """WebSocket handler - sends real-time job updates to connected clients."""
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client can send ping/pong or commands
            data = await ws.receive_text()
            # Echo back for ping/pong
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
