"""Kick.com scraper using the public API.

No API key required. Kick exposes a public REST API.
Supports: channels, streams, VODs, clips, categories, search.
"""

import logging
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

KICK_API = "https://kick.com/api"
KICK_BASE = "https://kick.com"


class KickScraper(BaseScraper):
    """Kick.com scraper using the public API.

    Kick has a public API that doesn't require authentication.

    Usage:
        scraper = KickScraper()
        results = await scraper.scrape_profile("xqc")
        results = await scraper.scrape_posts("xqc", max_results=20)
        results = await scraper.search("gaming", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "kick"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Kick channel profile.

        Args:
            identifier: Channel slug/username or URL.
        """
        slug = self._normalize_slug(identifier)

        # Kick's channel API endpoint
        url = f"{KICK_API}/v2/channels/{slug}"
        data = await self.fetch_json(url)

        livestream = data.get("livestream")

        profile = {
            "channel_id": data.get("id", ""),
            "slug": data.get("slug", slug),
            "username": data.get("user", {}).get("username", slug),
            "bio": data.get("user", {}).get("bio", ""),
            "avatar": data.get("user", {}).get("profile_pic", ""),
            "verified": data.get("verified", False),
            "follower_count": data.get("followers_count", 0),
            "is_live": livestream is not None,
            "current_stream": {
                "title": livestream.get("session_title", ""),
                "viewers": livestream.get("viewer_count", 0),
                "category": livestream.get("categories", [{}])[0].get("name", "") if livestream.get("categories") else "",
                "started_at": livestream.get("created_at", ""),
                "thumbnail": livestream.get("thumbnail", {}).get("url", "") if isinstance(livestream.get("thumbnail"), dict) else "",
            } if livestream else None,
            "banner": data.get("banner_image", {}).get("url", "") if isinstance(data.get("banner_image"), dict) else "",
            "url": f"{KICK_BASE}/{slug}",
        }

        return [self.make_result(ContentType.PROFILE, profile, url=profile["url"])]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape VODs from a Kick channel.

        Args:
            source: Channel slug or URL.
            max_results: Maximum VODs.
        """
        limit = max_results or self.config.max_results
        slug = self._normalize_slug(source)

        url = f"{KICK_API}/v2/channels/{slug}/videos"
        data = await self.fetch_json(url)

        videos = data if isinstance(data, list) else data.get("data", data.get("videos", []))

        results = []
        for video in videos[:limit]:
            vod = {
                "video_id": video.get("id", ""),
                "title": video.get("session_title", "") or video.get("title", ""),
                "created_at": video.get("created_at", ""),
                "duration": video.get("duration", ""),
                "view_count": video.get("views", 0) or video.get("view_count", 0),
                "thumbnail": video.get("thumbnail", ""),
                "category": (video.get("categories", [{}])[0].get("name", "")
                            if video.get("categories") else
                            video.get("category", {}).get("name", "") if isinstance(video.get("category"), dict) else ""),
                "url": f"{KICK_BASE}/{slug}/video/{video.get('uuid', video.get('id', ''))}",
            }
            results.append(
                self.make_result(ContentType.VIDEO, vod, url=vod["url"])
            )

        return results

    async def scrape_clips(
        self, channel: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape clips from a channel.

        Args:
            channel: Channel slug.
            max_results: Maximum clips.
        """
        limit = max_results or self.config.max_results
        slug = self._normalize_slug(channel)

        url = f"{KICK_API}/v2/channels/{slug}/clips"
        data = await self.fetch_json(url)

        clips = data.get("clips", data) if isinstance(data, dict) else data

        results = []
        items = clips if isinstance(clips, list) else clips.get("data", [])
        for clip in items[:limit]:
            clip_data = {
                "clip_id": clip.get("id", ""),
                "title": clip.get("title", ""),
                "created_at": clip.get("created_at", ""),
                "duration": clip.get("duration", 0),
                "view_count": clip.get("views", 0) or clip.get("view_count", 0),
                "likes": clip.get("likes", 0),
                "thumbnail": clip.get("thumbnail_url", ""),
                "creator": clip.get("creator", {}).get("username", "") if isinstance(clip.get("creator"), dict) else "",
                "category": clip.get("category", {}).get("name", "") if isinstance(clip.get("category"), dict) else "",
                "url": clip.get("clip_url", "") or f"{KICK_BASE}/{slug}/clips/{clip.get('id', '')}",
            }
            results.append(
                self.make_result(ContentType.VIDEO, clip_data, url=clip_data["url"])
            )

        return results

    async def scrape_live_streams(
        self, category: str | None = None, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape currently live streams.

        Args:
            category: Optional category to filter by.
            max_results: Maximum streams.
        """
        limit = max_results or self.config.max_results

        if category:
            url = f"{KICK_API}/v1/subcategories/{category}"
        else:
            url = f"{KICK_API}/v2/channels?livestream=1"

        data = await self.fetch_json(url)

        results = []
        channels = data if isinstance(data, list) else data.get("data", data.get("channels", []))

        for ch in channels[:limit]:
            livestream = ch.get("livestream") or ch
            stream = {
                "channel": ch.get("slug", "") or ch.get("channel", {}).get("slug", ""),
                "title": livestream.get("session_title", "") or livestream.get("title", ""),
                "viewers": livestream.get("viewer_count", 0) or livestream.get("viewers", 0),
                "category": (ch.get("categories", [{}])[0].get("name", "")
                            if ch.get("categories") else ""),
                "thumbnail": livestream.get("thumbnail", {}).get("url", "") if isinstance(livestream.get("thumbnail"), dict) else "",
                "url": f"{KICK_BASE}/{ch.get('slug', '')}",
            }
            results.append(
                self.make_result(ContentType.STREAM, stream, url=stream["url"])
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Kick for channels and categories.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        url = f"{KICK_API}/v1/search"
        params = {"query": query}
        data = await self.fetch_json(url, params=params)

        results = []

        # Channels
        for ch in data.get("channels", []):
            if len(results) >= limit:
                break
            channel = {
                "type": "channel",
                "channel_id": ch.get("id", ""),
                "slug": ch.get("slug", ""),
                "username": ch.get("user", {}).get("username", "") if isinstance(ch.get("user"), dict) else "",
                "is_live": ch.get("is_live", False) or ch.get("livestream") is not None,
                "follower_count": ch.get("followers_count", 0),
                "url": f"{KICK_BASE}/{ch.get('slug', '')}",
            }
            results.append(
                self.make_result(ContentType.SEARCH, channel, url=channel["url"])
            )

        # Categories
        for cat in data.get("categories", []):
            if len(results) >= limit:
                break
            category = {
                "type": "category",
                "category_id": cat.get("id", ""),
                "name": cat.get("name", ""),
                "slug": cat.get("slug", ""),
                "url": f"{KICK_BASE}/category/{cat.get('slug', '')}",
            }
            results.append(
                self.make_result(ContentType.SEARCH, category, url=category["url"])
            )

        return results[:limit]

    def _normalize_slug(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier.lstrip("@").lower()
