"""TikTok scraper using Playwright browser automation.

No API key required. Scrapes public TikTok data via browser automation.
Supports: profiles, videos, hashtags, search, trending.
"""

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

TIKTOK_BASE = "https://www.tiktok.com"


class TikTokScraper(BaseScraper):
    """TikTok scraper using Playwright browser automation.

    Usage:
        scraper = TikTokScraper()
        results = await scraper.scrape_profile("tiktok")
        results = await scraper.scrape_posts("tiktok", max_results=20)
        results = await scraper.search("cooking recipes", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._browser = None
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "tiktok"

    async def _get_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            stealth_cfg = await self._stealth.playwright_stealth_config()
            self._browser = await self._pw.chromium.launch(
                headless=self.config.headless,
                args=stealth_cfg["launch_args"]["args"],
            )
        return self._browser

    async def _new_page(self):
        browser = await self._get_browser()
        stealth_cfg = await self._stealth.playwright_stealth_config()
        context = await browser.new_context(**stealth_cfg["context_args"])
        page = await context.new_page()
        for script in stealth_cfg["stealth_scripts"]:
            await page.add_init_script(script)
        return page

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a TikTok user profile.

        Args:
            identifier: Username (with or without @) or profile URL.
        """
        username = self._normalize_username(identifier)
        page = await self._new_page()

        try:
            url = f"{TIKTOK_BASE}/@{username}"
            api_data = []

            async def intercept(response):
                if "api" in response.url and "user" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Try API data first
            profile = self._extract_profile_from_api(api_data, username)

            if not profile:
                # Fallback: parse from SIGI_STATE or HTML
                content = await page.content()
                profile = self._extract_profile_from_html(content, username)

            profile["url"] = url
            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await page.context.close()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape videos from a TikTok user.

        Args:
            source: Username or profile URL.
            max_results: Maximum videos to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        page = await self._new_page()

        try:
            url = f"{TIKTOK_BASE}/@{username}"
            api_data = []

            async def intercept(response):
                resp_url = response.url
                if "api" in resp_url and ("item_list" in resp_url or "post" in resp_url):
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            videos = []
            scroll_count = 0

            while len(videos) < limit and scroll_count < 20:
                # Extract from API responses
                for data in api_data:
                    self._extract_videos_from_api(data, videos, limit)
                api_data.clear()

                if len(videos) >= limit:
                    break

                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await page.wait_for_timeout(2000)
                scroll_count += 1

            # Fallback: parse from HTML / SIGI_STATE
            if not videos:
                content = await page.content()
                videos = self._extract_videos_from_html(content, username, limit)

            results = []
            for video in videos[:limit]:
                results.append(
                    self.make_result(ContentType.VIDEO, video, url=video.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def scrape_hashtag(
        self, hashtag: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape videos from a hashtag page.

        Args:
            hashtag: Hashtag (with or without #).
        """
        limit = max_results or self.config.max_results
        tag = hashtag.lstrip("#")
        page = await self._new_page()

        try:
            url = f"{TIKTOK_BASE}/tag/{tag}"
            api_data = []

            async def intercept(response):
                if "api" in response.url and ("challenge" in response.url or "tag" in response.url):
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            videos = []
            for data in api_data:
                self._extract_videos_from_api(data, videos, limit)

            if not videos:
                content = await page.content()
                videos = self._extract_videos_from_html(content, "", limit)

            results = []
            for video in videos[:limit]:
                video["hashtag"] = tag
                results.append(
                    self.make_result(ContentType.HASHTAG, video, url=video.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search TikTok.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        page = await self._new_page()

        try:
            url = f"{TIKTOK_BASE}/search?q={quote(query)}"
            api_data = []

            async def intercept(response):
                if "api" in response.url and "search" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            videos = []
            for data in api_data:
                self._extract_videos_from_api(data, videos, limit)

            if not videos:
                content = await page.content()
                videos = self._extract_videos_from_html(content, "", limit)

            results = []
            for video in videos[:limit]:
                results.append(
                    self.make_result(ContentType.SEARCH, video, url=video.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            for part in parts:
                if part.startswith("@"):
                    return part[1:]
            return parts[-1]
        return identifier.lstrip("@")

    def _extract_profile_from_api(self, api_data: list[dict], username: str) -> dict:
        for data in api_data:
            user = self._find_nested(data, ["userInfo", "user"])
            stats = self._find_nested(data, ["userInfo", "stats"])
            if user:
                return {
                    "username": user.get("uniqueId", username),
                    "nickname": user.get("nickname", ""),
                    "bio": user.get("signature", ""),
                    "verified": user.get("verified", False),
                    "avatar": user.get("avatarLarger", "") or user.get("avatarMedium", ""),
                    "follower_count": (stats or {}).get("followerCount", 0),
                    "following_count": (stats or {}).get("followingCount", 0),
                    "like_count": (stats or {}).get("heartCount", 0) or (stats or {}).get("heart", 0),
                    "video_count": (stats or {}).get("videoCount", 0),
                    "private": user.get("privateAccount", False),
                }
        return {}

    def _extract_profile_from_html(self, html: str, username: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # Try to find SIGI_STATE JSON
        sigi_script = soup.find("script", id="SIGI_STATE")
        if not sigi_script:
            sigi_script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")

        if sigi_script and sigi_script.string:
            try:
                sigi_data = json.loads(sigi_script.string)
                profile = self._extract_profile_from_api([sigi_data], username)
                if profile:
                    return profile
            except json.JSONDecodeError:
                pass

        # Fallback to meta tags
        return {
            "username": username,
            "nickname": self._meta(soup, "og:title") or username,
            "bio": self._meta(soup, "og:description") or "",
            "avatar": self._meta(soup, "og:image") or "",
        }

    def _extract_videos_from_api(
        self, data: Any, videos: list[dict], limit: int, seen: set | None = None
    ):
        if seen is None:
            seen = set()
        if len(videos) >= limit:
            return
        if isinstance(data, dict):
            video_id = data.get("id")
            desc = data.get("desc")
            stats = data.get("stats")
            if video_id and desc is not None and stats and str(video_id) not in seen:
                seen.add(str(video_id))
                author = data.get("author", {})
                video = {
                    "video_id": str(video_id),
                    "description": desc,
                    "author": author.get("uniqueId", ""),
                    "author_nickname": author.get("nickname", ""),
                    "play_count": stats.get("playCount", 0),
                    "like_count": stats.get("diggCount", 0) or stats.get("likeCount", 0),
                    "comment_count": stats.get("commentCount", 0),
                    "share_count": stats.get("shareCount", 0),
                    "save_count": stats.get("collectCount", 0),
                    "duration": data.get("video", {}).get("duration", 0),
                    "cover": data.get("video", {}).get("cover", ""),
                    "music_title": data.get("music", {}).get("title", ""),
                    "music_author": data.get("music", {}).get("authorName", ""),
                    "hashtags": [
                        c.get("hashtagName", "") for c in data.get("challenges", [])
                    ],
                    "created_time": data.get("createTime"),
                    "url": f"{TIKTOK_BASE}/@{author.get('uniqueId', '')}/video/{video_id}",
                }
                videos.append(video)

            for v in data.values():
                self._extract_videos_from_api(v, videos, limit, seen)
        elif isinstance(data, list):
            for item in data:
                self._extract_videos_from_api(item, videos, limit, seen)

    def _extract_videos_from_html(self, html: str, username: str, limit: int) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        videos = []

        # Try SIGI_STATE
        sigi_script = soup.find("script", id="SIGI_STATE")
        if not sigi_script:
            sigi_script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")

        if sigi_script and sigi_script.string:
            try:
                sigi_data = json.loads(sigi_script.string)
                self._extract_videos_from_api(sigi_data, videos, limit)
                if videos:
                    return videos
            except json.JSONDecodeError:
                pass

        # Fallback: parse video links from HTML
        for link in soup.find_all("a", href=re.compile(r"/video/\d+")):
            href = link["href"]
            if not href.startswith("http"):
                href = f"{TIKTOK_BASE}{href}"
            video_id = href.split("/video/")[-1].split("?")[0]
            videos.append({
                "video_id": video_id,
                "url": href,
                "author": username,
            })
            if len(videos) >= limit:
                break

        return videos

    @staticmethod
    def _find_nested(data: dict, keys: list[str]) -> Any:
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw"):
            await self._pw.stop()
        await super().close()
