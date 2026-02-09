"""Platform listing endpoints."""

from fastapi import APIRouter

from api.schemas import PlatformInfo
from config.settings import PLATFORMS

router = APIRouter(prefix="/api/platforms", tags=["platforms"])


@router.get("", response_model=list[PlatformInfo])
async def list_platforms():
    """List all available scraper platforms."""
    return [
        PlatformInfo(name=name, module=info["module"], rate_limit=info["rate_limit"])
        for name, info in sorted(PLATFORMS.items())
    ]


@router.get("/{name}")
async def get_platform(name: str):
    """Get details for a specific platform."""
    if name not in PLATFORMS:
        return {"error": f"Unknown platform: {name}"}
    info = PLATFORMS[name]
    return {
        "name": name,
        "module": info["module"],
        "class": info["class"],
        "rate_limit": info["rate_limit"],
        "actions": ["profile", "posts", "search"],
    }
