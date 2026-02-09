"""Threads scraper using Playwright browser automation.

No API key required. Scrapes public Threads posts via browser automation.
Supports: profiles, posts, search.
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

THREADS_BASE = "https://www.threads.net"


class ThreadsScraper(BaseScraper):
    """Threads scraper using Playwright.

    Usage:
        scraper = ThreadsScraper()
        results = await scraper.scrape_profile("zuck")
        results = await scraper.scrape_posts("zuck", max_results=20)
        results = await scraper.search("AI news", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._browser = None
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "threads"

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
        """Scrape a Threads profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        page = await self._new_page()

        try:
            url = f"{THREADS_BASE}/@{username}"
            api_data = []

            async def intercept(response):
                if "graphql" in response.url or "api/v1/users" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Try API data
            profile = {}
            for data in api_data:
                user = self._find_user_in_data(data)
                if user:
                    profile = {
                        "username": user.get("username", username),
                        "full_name": user.get("full_name", ""),
                        "biography": user.get("biography", "") or user.get("bio_text", ""),
                        "follower_count": user.get("follower_count", 0) or user.get("text_post_app_follower_count", 0),
                        "is_verified": user.get("is_verified", False),
                        "profile_pic": user.get("profile_pic_url", "") or user.get("hd_profile_pic_versions", [{}])[-1].get("url", ""),
                    }
                    break

            if not profile:
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                profile = {
                    "username": username,
                    "full_name": self._meta(soup, "og:title") or username,
                    "biography": self._meta(soup, "og:description") or "",
                    "profile_pic": self._meta(soup, "og:image") or "",
                }

            profile["url"] = url
            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await page.context.close()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a Threads profile.

        Args:
            source: Username or profile URL.
            max_results: Maximum posts.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        page = await self._new_page()

        try:
            url = f"{THREADS_BASE}/@{username}"
            api_data = []

            async def intercept(response):
                resp_url = response.url
                if "graphql" in resp_url or "text_post_app_thread" in resp_url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            posts = []
            scroll_count = 0

            while len(posts) < limit and scroll_count < 15:
                for data in api_data:
                    self._extract_threads_from_api(data, posts, limit)
                api_data.clear()

                if len(posts) >= limit:
                    break

                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(2000)
                scroll_count += 1

            # Fallback: HTML parsing
            if not posts:
                content = await page.content()
                posts = self._extract_threads_from_html(content, username, limit)

            results = []
            for post in posts[:limit]:
                results.append(
                    self.make_result(ContentType.POST, post, url=post.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Threads.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        page = await self._new_page()

        try:
            url = f"{THREADS_BASE}/search?q={quote(query)}&serp_type=default"
            api_data = []

            async def intercept(response):
                if "search" in response.url and "graphql" in response.url:
                    try:
                        data = await response.json()
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", intercept)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            posts = []
            for data in api_data:
                self._extract_threads_from_api(data, posts, limit)

            results = []
            for post in posts[:limit]:
                results.append(
                    self.make_result(ContentType.SEARCH, post, url=post.get("url", ""))
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

    def _find_user_in_data(self, data: Any) -> dict | None:
        if isinstance(data, dict):
            if "username" in data and ("biography" in data or "follower_count" in data or "bio_text" in data):
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

    def _extract_threads_from_api(
        self, data: Any, posts: list[dict], limit: int, seen: set | None = None
    ):
        if seen is None:
            seen = set()
        if len(posts) >= limit:
            return
        if isinstance(data, dict):
            # Look for thread/post objects
            post_id = data.get("id") or data.get("pk")
            text_content = data.get("text") or data.get("caption")
            if post_id and text_content is not None and str(post_id) not in seen:
                # Check if this looks like a Threads post
                user = data.get("user", data.get("text_post_app_info", {}).get("user", {}))
                if isinstance(user, dict) and user.get("username"):
                    seen.add(str(post_id))
                    username = user.get("username", "")
                    code = data.get("code", "")
                    post = {
                        "post_id": str(post_id),
                        "text": text_content if isinstance(text_content, str) else (text_content or {}).get("text", ""),
                        "author": username,
                        "author_name": user.get("full_name", ""),
                        "like_count": data.get("like_count", 0),
                        "reply_count": data.get("text_post_app_info", {}).get("reply_count", 0) if isinstance(data.get("text_post_app_info"), dict) else 0,
                        "repost_count": data.get("repost_count", 0),
                        "created_at": data.get("taken_at"),
                        "url": f"{THREADS_BASE}/@{username}/post/{code}" if code else "",
                    }
                    posts.append(post)

            for v in data.values():
                self._extract_threads_from_api(v, posts, limit, seen)
        elif isinstance(data, list):
            for item in data:
                self._extract_threads_from_api(item, posts, limit, seen)

    def _extract_threads_from_html(
        self, html: str, username: str, limit: int
    ) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        posts = []

        # Look for post containers in the HTML
        for div in soup.find_all("div", {"data-pressable-container": True}):
            text_div = div.find("div", class_=re.compile(r"text"))
            if not text_div:
                continue
            text = text_div.get_text(strip=True)
            if text:
                posts.append({
                    "text": text,
                    "author": username,
                })
                if len(posts) >= limit:
                    break

        return posts

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
