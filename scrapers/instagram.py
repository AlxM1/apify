"""Instagram scraper using Playwright browser automation.

No API key required. Uses browser automation to access Instagram's web interface
and intercepts the backend JSON API responses.
Supports: profiles, posts, reels, comments, hashtags, search.
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

INSTAGRAM_BASE = "https://www.instagram.com"


class InstagramScraper(BaseScraper):
    """Instagram scraper using Playwright with stealth.

    Scrapes public Instagram data via browser automation and API interception.

    Usage:
        scraper = InstagramScraper()
        results = await scraper.scrape_profile("instagram")
        results = await scraper.scrape_posts("instagram", max_results=20)
        results = await scraper.search("travel", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._browser = None
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "instagram"

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
        """Scrape an Instagram profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        page = await self._new_page()

        try:
            api_data = []

            async def intercept_response(response):
                url = response.url
                if "graphql" in url or "api/v1/users" in url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept_response)

            url = f"{INSTAGRAM_BASE}/{username}/"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Try to extract from API responses first
            profile = self._extract_profile_from_api(api_data, username)

            if not profile:
                # Fallback to HTML meta tags
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                profile = self._extract_profile_from_html(soup, username)

            profile["url"] = f"{INSTAGRAM_BASE}/{username}/"
            return [self.make_result(ContentType.PROFILE, profile, url=profile["url"])]
        finally:
            await page.context.close()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from an Instagram profile.

        Args:
            source: Username or profile URL.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        page = await self._new_page()

        try:
            api_data = []

            async def intercept_response(response):
                url = response.url
                if "graphql" in url or "api/v1/feed" in url or "api/v1/users" in url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept_response)

            url = f"{INSTAGRAM_BASE}/{username}/"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Scroll to load more posts
            posts = []
            scroll_count = 0
            while len(posts) < limit and scroll_count < 20:
                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await page.wait_for_timeout(2000)
                scroll_count += 1

                for data in api_data:
                    self._extract_posts_from_api(data, posts, limit)
                api_data.clear()

            # Fallback: extract from HTML
            if not posts:
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                posts = self._extract_posts_from_html(soup, username, limit)

            results = []
            for post in posts[:limit]:
                results.append(
                    self.make_result(ContentType.POST, post, url=post.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def scrape_hashtag(
        self, hashtag: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a hashtag page.

        Args:
            hashtag: Hashtag (with or without #).
            max_results: Maximum posts.
        """
        limit = max_results or self.config.max_results
        tag = hashtag.lstrip("#")
        page = await self._new_page()

        try:
            api_data = []

            async def intercept_response(response):
                if "graphql" in response.url or "api/v1/tags" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept_response)

            url = f"{INSTAGRAM_BASE}/explore/tags/{tag}/"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            posts = []
            for data in api_data:
                self._extract_posts_from_api(data, posts, limit)

            results = []
            for post in posts[:limit]:
                post["hashtag"] = tag
                results.append(
                    self.make_result(ContentType.HASHTAG, post, url=post.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Instagram (users and hashtags).

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        page = await self._new_page()

        try:
            api_data = []

            async def intercept_response(response):
                if "web_search" in response.url or "topsearch" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept_response)

            url = f"{INSTAGRAM_BASE}/explore/search/keyword/?q={quote(query)}"
            await page.goto(
                f"{INSTAGRAM_BASE}", wait_until="networkidle", timeout=30000
            )
            await page.wait_for_timeout(2000)

            # Type into search
            search_input = page.locator('input[placeholder="Search"]').first
            if await search_input.is_visible():
                await search_input.click()
                await search_input.fill(query)
                await page.wait_for_timeout(3000)

            results = []
            for data in api_data:
                # Extract users from search results
                users = data.get("users", [])
                for user_item in users:
                    user = user_item.get("user", user_item)
                    profile = {
                        "username": user.get("username", ""),
                        "full_name": user.get("full_name", ""),
                        "profile_pic": user.get("profile_pic_url", ""),
                        "is_verified": user.get("is_verified", False),
                        "follower_count": user.get("follower_count"),
                    }
                    results.append(
                        self.make_result(
                            ContentType.SEARCH,
                            profile,
                            url=f"{INSTAGRAM_BASE}/{profile['username']}/",
                        )
                    )
                    if len(results) >= limit:
                        break

            return results[:limit]
        finally:
            await page.context.close()

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier.lstrip("@")

    def _extract_profile_from_api(self, api_data: list[dict], username: str) -> dict:
        for data in api_data:
            user = self._find_user_in_data(data)
            if user:
                return {
                    "username": user.get("username", username),
                    "full_name": user.get("full_name", ""),
                    "biography": user.get("biography", ""),
                    "follower_count": user.get("edge_followed_by", {}).get("count")
                        or user.get("follower_count", 0),
                    "following_count": user.get("edge_follow", {}).get("count")
                        or user.get("following_count", 0),
                    "post_count": user.get("edge_owner_to_timeline_media", {}).get("count")
                        or user.get("media_count", 0),
                    "is_verified": user.get("is_verified", False),
                    "is_private": user.get("is_private", False),
                    "profile_pic": user.get("profile_pic_url_hd", "")
                        or user.get("profile_pic_url", ""),
                    "external_url": user.get("external_url", ""),
                    "category": user.get("category_name", ""),
                }
        return {}

    def _find_user_in_data(self, data: Any) -> dict | None:
        if isinstance(data, dict):
            if "username" in data and ("biography" in data or "follower_count" in data or "edge_followed_by" in data):
                return data
            for v in data.values():
                result = self._find_user_in_data(v)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_user_in_data(item)
                if result:
                    return result
        return None

    def _extract_profile_from_html(self, soup: BeautifulSoup, username: str) -> dict:
        description = self._meta(soup, "og:description") or ""
        # Parse "X Followers, Y Following, Z Posts" from description
        followers = following = posts = 0
        match = re.search(r"([\d,.]+[KMB]?)\s*Followers", description)
        if match:
            followers = self._parse_count(match.group(1))
        match = re.search(r"([\d,.]+[KMB]?)\s*Following", description)
        if match:
            following = self._parse_count(match.group(1))
        match = re.search(r"([\d,.]+[KMB]?)\s*Posts", description)
        if match:
            posts = self._parse_count(match.group(1))

        return {
            "username": username,
            "full_name": self._meta(soup, "og:title") or username,
            "biography": "",
            "follower_count": followers,
            "following_count": following,
            "post_count": posts,
            "profile_pic": self._meta(soup, "og:image") or "",
        }

    def _extract_posts_from_api(
        self, data: Any, posts: list[dict], limit: int, seen: set | None = None
    ):
        if seen is None:
            seen = set()
        if len(posts) >= limit:
            return
        if isinstance(data, dict):
            # Check if this looks like a media node
            shortcode = data.get("shortcode") or data.get("code")
            if shortcode and shortcode not in seen and "edge_liked_by" in data or "like_count" in data:
                seen.add(shortcode)
                post = {
                    "shortcode": shortcode,
                    "post_id": data.get("id", ""),
                    "caption": self._get_caption(data),
                    "like_count": data.get("edge_liked_by", {}).get("count")
                        or data.get("edge_media_preview_like", {}).get("count")
                        or data.get("like_count", 0),
                    "comment_count": data.get("edge_media_to_comment", {}).get("count")
                        or data.get("comment_count", 0),
                    "is_video": data.get("is_video", False),
                    "video_view_count": data.get("video_view_count", 0),
                    "display_url": data.get("display_url", "") or data.get("image_versions2", {}).get("candidates", [{}])[0].get("url", ""),
                    "thumbnail": data.get("thumbnail_src", ""),
                    "taken_at": data.get("taken_at_timestamp") or data.get("taken_at"),
                    "url": f"{INSTAGRAM_BASE}/p/{shortcode}/",
                }
                posts.append(post)

            for v in data.values():
                self._extract_posts_from_api(v, posts, limit, seen)
        elif isinstance(data, list):
            for item in data:
                self._extract_posts_from_api(item, posts, limit, seen)

    def _extract_posts_from_html(
        self, soup: BeautifulSoup, username: str, limit: int
    ) -> list[dict]:
        posts = []
        for link in soup.find_all("a", href=re.compile(r"/p/[^/]+/")):
            href = link["href"]
            shortcode = href.strip("/").split("/")[-1]
            img = link.find("img")
            post = {
                "shortcode": shortcode,
                "url": f"{INSTAGRAM_BASE}{href}",
                "thumbnail": img.get("src", "") if img else "",
                "alt_text": img.get("alt", "") if img else "",
                "author": username,
            }
            posts.append(post)
            if len(posts) >= limit:
                break
        return posts

    @staticmethod
    def _get_caption(data: dict) -> str:
        edges = data.get("edge_media_to_caption", {}).get("edges", [])
        if edges:
            return edges[0].get("node", {}).get("text", "")
        caption = data.get("caption")
        if isinstance(caption, dict):
            return caption.get("text", "")
        if isinstance(caption, str):
            return caption
        return ""

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip().replace(",", "")
        multiplier = 1
        if text.endswith("K"):
            multiplier, text = 1000, text[:-1]
        elif text.endswith("M"):
            multiplier, text = 1000000, text[:-1]
        elif text.endswith("B"):
            multiplier, text = 1000000000, text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw"):
            await self._pw.stop()
        await super().close()
