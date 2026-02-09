"""Sina Weibo scraper using stealth web scraping and AJAX JSON parsing.

No API key required. Scrapes Weibo's mobile web interface (m.weibo.cn) which
returns clean JSON from its AJAX endpoints. Uses stealth headers to avoid
bot detection. The mobile API endpoints are more accessible than the desktop
site and return structured JSON responses.

Supports: user profiles, posts (weibos), search.
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

# Weibo mobile endpoints return JSON and are easier to work with
WEIBO_MOBILE_API = "https://m.weibo.cn/api"
WEIBO_MOBILE = "https://m.weibo.cn"
WEIBO_BASE = "https://weibo.com"


class WeiboScraper(BaseScraper):
    """Sina Weibo scraper using mobile AJAX endpoints and stealth headers.

    Weibo's mobile web interface (m.weibo.cn) exposes AJAX endpoints that
    return JSON data for profiles, timelines, and search. These endpoints
    are publicly accessible without authentication for public content.
    A StealthSession is used for realistic browser fingerprints.

    Usage:
        scraper = WeiboScraper()
        results = await scraper.scrape_profile("1197161814")  # numeric UID
        results = await scraper.scrape_posts("1197161814", max_results=20)
        results = await scraper.search("Python", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "weibo"

    async def get_client(self):
        """Override to use stealth headers with Weibo-specific referer."""
        if self._client is None or self._client.is_closed:
            self._client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
            # Set Weibo-specific headers that the AJAX endpoints expect
            self._client.headers.update({
                "Referer": WEIBO_MOBILE,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/plain, */*",
            })
        return self._client

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Weibo user profile.

        Args:
            identifier: Numeric user ID (UID), custom domain, or full URL.
        """
        uid = self._normalize_uid(identifier)

        # Try the mobile API endpoint
        profile = await self._api_get_profile(uid)
        if profile:
            return [self.make_result(
                ContentType.PROFILE, profile, url=profile.get("url", f"{WEIBO_BASE}/u/{uid}")
            )]

        # Fallback: scrape the profile page HTML
        profile = await self._scrape_profile_page(uid)
        return [self.make_result(
            ContentType.PROFILE, profile, url=profile.get("url", f"{WEIBO_BASE}/u/{uid}")
        )]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts (weibos) from a user's timeline.

        Uses the mobile container AJAX endpoint for paginated JSON results.

        Args:
            source: Numeric user ID, custom domain, or full URL.
            max_results: Maximum posts to return.
        """
        limit = max_results or self.config.max_results
        uid = self._normalize_uid(source)

        # Get the user's containerid for their weibo timeline
        container_id = await self._get_container_id(uid)
        if not container_id:
            # Default containerid pattern for weibo tab
            container_id = f"107603{uid}"

        results: list[ScraperResult] = []
        page = 1

        while len(results) < limit:
            url = (
                f"{WEIBO_MOBILE_API}/container/getIndex"
                f"?type=uid&value={uid}&containerid={container_id}&page={page}"
            )

            try:
                data = await self.fetch_json(url)
            except Exception as e:
                logger.warning("Failed to fetch Weibo posts page %d for %s: %s", page, uid, e)
                break

            ok = data.get("ok")
            if ok != 1:
                logger.debug("Weibo API returned ok=%s for uid %s page %d", ok, uid, page)
                break

            cards = data.get("data", {}).get("cards", [])
            if not cards:
                break

            new_posts = 0
            for card in cards:
                if len(results) >= limit:
                    break
                # card_type 9 = regular weibo post
                if card.get("card_type") != 9:
                    continue
                mblog = card.get("mblog")
                if not mblog:
                    continue
                post_data = self._normalize_mblog(mblog)
                post_url = post_data.get("url", "")
                results.append(
                    self.make_result(ContentType.POST, post_data, url=post_url)
                )
                new_posts += 1

            if new_posts == 0:
                break

            page += 1

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Weibo for posts.

        Uses the mobile search AJAX endpoint.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        results: list[ScraperResult] = []
        page = 1

        while len(results) < limit:
            url = (
                f"{WEIBO_MOBILE_API}/container/getIndex"
                f"?containerid=100103type%3D1%26q%3D{quote(query)}&page_type=searchall"
                f"&page={page}"
            )

            try:
                data = await self.fetch_json(url)
            except Exception as e:
                logger.warning("Failed to fetch Weibo search page %d: %s", page, e)
                break

            ok = data.get("ok")
            if ok != 1:
                logger.debug("Weibo search API returned ok=%s for query '%s'", ok, query)
                # Fallback to HTML scraping
                if not results:
                    return await self._scrape_search_page(query, limit)
                break

            cards = data.get("data", {}).get("cards", [])
            if not cards:
                break

            new_results = 0
            for card in cards:
                if len(results) >= limit:
                    break

                # Search results may be grouped in card_group
                card_group = card.get("card_group", [])
                items = card_group if card_group else [card]

                for item in items:
                    if len(results) >= limit:
                        break
                    if item.get("card_type") != 9:
                        continue
                    mblog = item.get("mblog")
                    if not mblog:
                        continue
                    post_data = self._normalize_mblog(mblog)
                    post_url = post_data.get("url", "")
                    results.append(
                        self.make_result(ContentType.SEARCH, post_data, url=post_url)
                    )
                    new_results += 1

            if new_results == 0:
                break

            page += 1

        return results

    # ------------------------------------------------------------------
    # Mobile API helpers
    # ------------------------------------------------------------------

    async def _api_get_profile(self, uid: str) -> dict[str, Any] | None:
        """Fetch profile via the mobile API info endpoint."""
        url = f"{WEIBO_MOBILE_API}/container/getIndex?type=uid&value={uid}"

        try:
            data = await self.fetch_json(url)
        except Exception as e:
            logger.debug("Failed to fetch Weibo profile API for %s: %s", uid, e)
            return None

        if data.get("ok") != 1:
            return None

        userinfo = data.get("data", {}).get("userInfo")
        if not userinfo:
            return None

        return self._normalize_user(userinfo)

    async def _get_container_id(self, uid: str) -> str:
        """Discover the containerid for a user's weibo timeline tab."""
        url = f"{WEIBO_MOBILE_API}/container/getIndex?type=uid&value={uid}"

        try:
            data = await self.fetch_json(url)
        except Exception:
            return ""

        if data.get("ok") != 1:
            return ""

        tabs = data.get("data", {}).get("tabsInfo", {}).get("tabs", [])
        for tab in tabs:
            if tab.get("tab_type") == "weibo":
                return tab.get("containerid", "")

        return ""

    # ------------------------------------------------------------------
    # Web scraping fallbacks
    # ------------------------------------------------------------------

    async def _scrape_profile_page(self, uid: str) -> dict[str, Any]:
        """Scrape profile from the mobile web page as fallback."""
        url = f"{WEIBO_MOBILE}/u/{uid}"
        try:
            resp = await self.fetch(url)
        except Exception as e:
            logger.warning("Failed to scrape Weibo profile page for %s: %s", uid, e)
            return {"uid": uid, "url": f"{WEIBO_BASE}/u/{uid}"}

        soup = BeautifulSoup(resp.text, "lxml")

        # Try to extract __INITIAL_STATE__ or similar JSON blob
        profile = self._extract_embedded_json_profile(soup, uid)
        if profile:
            return profile

        # Meta tag fallback
        return {
            "uid": uid,
            "screen_name": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "avatar": self._meta(soup, "og:image") or "",
            "url": f"{WEIBO_BASE}/u/{uid}",
        }

    async def _scrape_search_page(self, query: str, limit: int) -> list[ScraperResult]:
        """Scrape search results from Weibo's mobile web search page."""
        url = f"{WEIBO_MOBILE}/search?containerid=100103type%3D1%26q%3D{quote(query)}"
        try:
            resp = await self.fetch(url)
        except Exception as e:
            logger.warning("Failed to scrape Weibo search page: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results: list[ScraperResult] = []

        # Try embedded JSON
        for script in soup.find_all("script"):
            if not script.string:
                continue
            # Look for render data or initial state
            match = re.search(
                r'(?:\$render_data|__INITIAL_STATE__|window\.data)\s*[=:]\s*(\[?\{.*?\}]?)\s*[;\n]',
                script.string, re.DOTALL,
            )
            if not match:
                continue
            try:
                render_data = json.loads(match.group(1))
                self._extract_posts_from_render(render_data, results, limit, ContentType.SEARCH)
                if results:
                    return results
            except json.JSONDecodeError:
                continue

        # HTML fallback for search
        for card in soup.find_all(class_=re.compile(r"card|weibo-text|m-text", re.IGNORECASE)):
            if len(results) >= limit:
                break
            text = card.get_text(separator=" ", strip=True)[:300]
            if not text or len(text) < 10:
                continue
            link = card.find("a", href=True)
            href = ""
            if link:
                href = link["href"]
                if not href.startswith("http"):
                    href = f"{WEIBO_MOBILE}{href}"
            entry = {
                "text": text,
                "url": href,
            }
            results.append(
                self.make_result(ContentType.SEARCH, entry, url=href)
            )

        return results

    # ------------------------------------------------------------------
    # Data normalization
    # ------------------------------------------------------------------

    def _normalize_user(self, userinfo: dict) -> dict[str, Any]:
        """Normalize a Weibo user info dict into our standard format."""
        return {
            "uid": userinfo.get("id"),
            "screen_name": userinfo.get("screen_name", ""),
            "description": userinfo.get("description", ""),
            "avatar": userinfo.get("avatar_hd", "") or userinfo.get("profile_image_url", ""),
            "cover": userinfo.get("cover_image_phone", ""),
            "gender": userinfo.get("gender", ""),
            "followers_count": userinfo.get("followers_count", 0),
            "following_count": userinfo.get("follow_count", 0),
            "posts_count": userinfo.get("statuses_count", 0),
            "verified": userinfo.get("verified", False),
            "verified_reason": userinfo.get("verified_reason", ""),
            "url": f"{WEIBO_BASE}/u/{userinfo.get('id', '')}",
        }

    def _normalize_mblog(self, mblog: dict) -> dict[str, Any]:
        """Normalize a Weibo mblog (post) object into our standard format."""
        # Clean HTML tags from text
        raw_text = mblog.get("text", "")
        if raw_text:
            text_soup = BeautifulSoup(raw_text, "lxml")
            clean_text = text_soup.get_text(separator=" ", strip=True)
        else:
            clean_text = ""

        # Extract images
        pics = mblog.get("pics", [])
        images = [pic.get("large", {}).get("url", "") or pic.get("url", "") for pic in pics]

        # Extract user info
        user = mblog.get("user", {}) or {}

        # Build the weibo URL
        mid = mblog.get("mid", "") or mblog.get("id", "")
        uid = user.get("id", "")
        post_url = f"{WEIBO_MOBILE}/detail/{mid}" if mid else ""

        # Retweeted post
        retweeted = mblog.get("retweeted_status")
        retweet_data = None
        if retweeted:
            retweet_data = {
                "text": BeautifulSoup(retweeted.get("text", ""), "lxml").get_text(separator=" ", strip=True),
                "user": retweeted.get("user", {}).get("screen_name", "") if retweeted.get("user") else "",
            }

        return {
            "post_id": str(mid),
            "text": clean_text,
            "created_at": mblog.get("created_at", ""),
            "source": BeautifulSoup(mblog.get("source", ""), "lxml").get_text(strip=True),
            "reposts_count": mblog.get("reposts_count", 0),
            "comments_count": mblog.get("comments_count", 0),
            "likes_count": mblog.get("attitudes_count", 0),
            "images": images,
            "author": user.get("screen_name", ""),
            "author_uid": uid,
            "author_verified": user.get("verified", False),
            "is_long_text": mblog.get("isLongText", False),
            "retweet": retweet_data,
            "url": post_url,
        }

    # ------------------------------------------------------------------
    # Embedded JSON extraction
    # ------------------------------------------------------------------

    def _extract_embedded_json_profile(
        self, soup: BeautifulSoup, uid: str
    ) -> dict[str, Any] | None:
        """Try to extract profile from inline JSON scripts in the page."""
        for script in soup.find_all("script"):
            if not script.string:
                continue
            match = re.search(
                r'(?:\$render_data|__INITIAL_STATE__|window\.data)\s*[=:]\s*(\[?\{.*?\}]?)\s*[;\n]',
                script.string, re.DOTALL,
            )
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            userinfo = self._find_user_in_data(data)
            if userinfo:
                return self._normalize_user(userinfo)

        return None

    def _find_user_in_data(self, data: Any) -> dict | None:
        """Recursively find a userInfo-like dict in nested data."""
        if isinstance(data, dict):
            if "screen_name" in data and ("followers_count" in data or "id" in data):
                return data
            if "userInfo" in data and isinstance(data["userInfo"], dict):
                return data["userInfo"]
            for value in data.values():
                result = self._find_user_in_data(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_user_in_data(item)
                if result:
                    return result
        return None

    def _extract_posts_from_render(
        self, data: Any, results: list[ScraperResult], limit: int,
        content_type: ContentType,
    ) -> None:
        """Recursively extract mblog posts from render/initial-state data."""
        if len(results) >= limit:
            return
        if isinstance(data, dict):
            if "mblog" in data and isinstance(data["mblog"], dict):
                mblog = data["mblog"]
                post_data = self._normalize_mblog(mblog)
                results.append(
                    self.make_result(content_type, post_data, url=post_data.get("url", ""))
                )
            else:
                for value in data.values():
                    self._extract_posts_from_render(value, results, limit, content_type)
        elif isinstance(data, list):
            for item in data:
                self._extract_posts_from_render(item, results, limit, content_type)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_uid(identifier: str) -> str:
        """Extract numeric UID from a URL or bare identifier."""
        if identifier.startswith("http"):
            # Handle URLs like weibo.com/u/123456 or weibo.com/username
            path = identifier.rstrip("/").split("?")[0]
            parts = path.split("/")
            # /u/123456
            if "u" in parts:
                idx = parts.index("u")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            # Last path component
            return parts[-1] if parts else identifier
        return identifier.strip().strip("/").strip("@")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        if tag:
            return tag.get("content", "")
        return ""
