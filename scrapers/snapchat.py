"""Snapchat scraper for public Spotlight and Discover content.

No API key required. Scrapes public Snapchat web content.
Limited: most Snapchat content is ephemeral and private.
Supports: public profiles, Spotlight videos, Discover stories.
"""

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

SNAPCHAT_BASE = "https://www.snapchat.com"
STORY_BASE = "https://story.snapchat.com"


class SnapchatScraper(BaseScraper):
    """Snapchat scraper for public content.

    Scrapes publicly accessible Snapchat data (Spotlight, Discover, public profiles).

    Usage:
        scraper = SnapchatScraper()
        results = await scraper.scrape_profile("snapchat")
        results = await scraper.scrape_posts("spotlight", max_results=20)
        results = await scraper.search("funny", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "snapchat"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a public Snapchat profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        url = f"{SNAPCHAT_BASE}/add/{username}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            profile = {
                "username": username,
                "display_name": self._meta(soup, "og:title") or username,
                "description": self._meta(soup, "og:description") or "",
                "avatar": self._meta(soup, "og:image") or "",
                "snapcode_url": f"https://app.snapchat.com/web/deeplink/snapcode?username={username}&type=SVG",
                "url": url,
            }

            # Try to extract from structured data
            for script in soup.find_all("script", {"type": "application/ld+json"}):
                if script.string:
                    try:
                        ld = json.loads(script.string)
                        if isinstance(ld, dict):
                            profile["name"] = ld.get("name", profile["display_name"])
                            profile["description"] = ld.get("description", profile["description"])
                    except json.JSONDecodeError:
                        pass

            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await client.aclose()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape public Snapchat stories or Spotlight content.

        Args:
            source: Username for public stories, or "spotlight"/"discover" for public feeds.
            max_results: Maximum items.
        """
        limit = max_results or self.config.max_results

        if source.lower() in ("spotlight", "discover"):
            return await self._scrape_spotlight(limit)

        # Scrape public story for a user
        return await self._scrape_public_story(source, limit)

    async def _scrape_public_story(self, username: str, limit: int) -> list[ScraperResult]:
        """Scrape a user's public story."""
        username = self._normalize_username(username)
        url = f"{STORY_BASE}/s/{username}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results = []

            # Look for story media in the page
            for video in soup.find_all("video", src=True):
                results.append(
                    self.make_result(
                        ContentType.STORY,
                        {
                            "type": "video",
                            "url": video["src"],
                            "poster": video.get("poster", ""),
                            "author": username,
                        },
                        url=url,
                    )
                )
                if len(results) >= limit:
                    break

            for img in soup.find_all("img", src=re.compile(r"story|snap|media")):
                results.append(
                    self.make_result(
                        ContentType.STORY,
                        {
                            "type": "image",
                            "url": img["src"],
                            "alt": img.get("alt", ""),
                            "author": username,
                        },
                        url=url,
                    )
                )
                if len(results) >= limit:
                    break

            # Also try embedded JSON
            for script in soup.find_all("script", {"type": "application/json"}):
                if script.string and len(results) < limit:
                    try:
                        data = json.loads(script.string)
                        self._extract_stories_from_data(data, results, username, limit)
                    except json.JSONDecodeError:
                        pass

            return results[:limit]
        finally:
            await client.aclose()

    async def _scrape_spotlight(self, limit: int) -> list[ScraperResult]:
        """Scrape Spotlight (TikTok-like public feed)."""
        url = f"{SNAPCHAT_BASE}/spotlight"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results = []

            # Extract Spotlight videos from the page
            for script in soup.find_all("script", {"type": "application/json"}):
                if script.string and len(results) < limit:
                    try:
                        data = json.loads(script.string)
                        self._extract_spotlight_from_data(data, results, limit)
                    except json.JSONDecodeError:
                        pass

            # Fallback: video elements
            if not results:
                for video in soup.find_all("video"):
                    src = video.get("src", "")
                    if src:
                        results.append(
                            self.make_result(
                                ContentType.VIDEO,
                                {"type": "spotlight", "url": src, "poster": video.get("poster", "")},
                                url=f"{SNAPCHAT_BASE}/spotlight",
                            )
                        )
                        if len(results) >= limit:
                            break

            return results[:limit]
        finally:
            await client.aclose()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Snapchat (limited to public profiles).

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Snapchat doesn't have a public search API
        # Try to find the user by username
        results = []
        try:
            profile_results = await self.scrape_profile(query)
            results.extend(profile_results)
        except Exception:
            pass

        return results[:limit]

    def _extract_stories_from_data(
        self, data: Any, results: list[ScraperResult], username: str, limit: int
    ):
        if len(results) >= limit:
            return
        if isinstance(data, dict):
            media_url = data.get("mediaUrl") or data.get("media_url")
            if media_url:
                story = {
                    "type": data.get("mediaType", data.get("type", "unknown")),
                    "url": media_url,
                    "duration": data.get("duration"),
                    "timestamp": data.get("timestamp") or data.get("created_at"),
                    "author": username,
                }
                results.append(self.make_result(ContentType.STORY, story, url=media_url))

            for v in data.values():
                self._extract_stories_from_data(v, results, username, limit)
        elif isinstance(data, list):
            for item in data:
                self._extract_stories_from_data(item, results, username, limit)

    def _extract_spotlight_from_data(
        self, data: Any, results: list[ScraperResult], limit: int
    ):
        if len(results) >= limit:
            return
        if isinstance(data, dict):
            # Look for video/snap objects
            snap_id = data.get("snapId") or data.get("id")
            media_url = data.get("snapMediaUrl") or data.get("mediaUrl") or data.get("media_url")
            if snap_id and media_url:
                video = {
                    "snap_id": str(snap_id),
                    "media_url": media_url,
                    "caption": data.get("caption", "") or data.get("title", ""),
                    "view_count": data.get("viewCount", 0),
                    "type": "spotlight",
                }
                results.append(
                    self.make_result(ContentType.VIDEO, video, url=media_url)
                )

            for v in data.values():
                self._extract_spotlight_from_data(v, results, limit)
        elif isinstance(data, list):
            for item in data:
                self._extract_spotlight_from_data(item, results, limit)

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier.lstrip("@")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
