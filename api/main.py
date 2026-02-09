"""FastAPI application – serves the API and the React frontend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.config import settings
from api.database import init_db
from api.routes import bulk, dashboard, platforms, results, schedules, scrapes, webhooks
from api.ws import websocket_endpoint

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# ── Rate limiter ──────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit] if settings.rate_limit_enabled else [],
    enabled=settings.rate_limit_enabled,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Start scheduler
    from api.scheduler import start_scheduler
    start_scheduler()

    # Start retention cleanup
    from api.retention import start_retention
    start_retention()

    yield

    # Shutdown
    from api.scheduler import stop_scheduler
    from api.retention import stop_retention
    stop_scheduler()
    stop_retention()


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="Self-hosted social media scraper with 20 platform scrapers",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────
app.include_router(dashboard.router)
app.include_router(platforms.router)
app.include_router(scrapes.router)
app.include_router(results.router)
app.include_router(schedules.router)
app.include_router(webhooks.router)
app.include_router(bulk.router)

# ── WebSocket ─────────────────────────────────────────────────
app.add_api_websocket_route("/ws", websocket_endpoint)

# ── Auth info endpoint ────────────────────────────────────────

@app.get("/api/auth/status")
async def auth_status():
    """Check if authentication is enabled."""
    return {
        "auth_enabled": bool(settings.api_key),
        "methods": ["X-API-Key header", "Bearer JWT token"] if settings.api_key else [],
    }


# ── Serve React frontend (static files) ──────────────────────
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        """Serve the React SPA – all non-API routes fall through to index.html."""
        file = FRONTEND_DIR / path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIR / "index.html")
else:

    @app.get("/")
    async def root():
        return {
            "message": "Apify Scraper API is running. Frontend not built yet.",
            "docs": "/docs",
            "build_frontend": "cd frontend && npm install && npm run build",
        }
