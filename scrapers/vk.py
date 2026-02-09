"""VK (VKontakte) scraper using public API and web scraping fallback.

Some VK API endpoints work without authentication (users.get, wall.get for
public profiles, etc.) via the VK API v5.199. For endpoints that require a
token or when the API is unavailable, falls back to scraping VK's mobile
web pages which are lighter and easier to parse.

Supports: user/group profiles, wall posts, search.
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

VK_API = "https://api.vk.com/method"
VK_API_VERSION = "5.199"
VK_BASE = "https://vk.com"
VK_MOBILE = "https://m.vk.com"


class VKScraper(BaseScraper):
    """VK (VKontakte) scraper using the public API with web scraping fallback.

    The VK API allows some public data access without an access token. When
    a token is available (passed via config.custom_headers["vk_token"]), it
    is used for broader access. When API calls fail, the scraper falls back
    to parsing VK's mobile web interface.

    Usage:
        scraper = VKScraper()
        results = await scraper.scrape_profile("durov")
        results = await scraper.scrape_posts("durov", max_results=20)
        results = await scraper.search("programming", max_results=20)

        # With token for broader access:
        config = ScraperConfig(custom_headers={"vk_token": "your_token"})
        scraper = VKScraper(config)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()
        self._token: str = self.config.custom_headers.get("vk_token", "")

    @property
    def platform_name(self) -> str:
        return "vk"

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a VK user or community profile.

        Args:
            identifier: Username, numeric ID, or full VK URL.
        """
        screen_name = self._normalize_identifier(identifier)

        # Try API first
        profile = await self._api_get_profile(screen_name)
        if profile:
            return [self.make_result(
                ContentType.PROFILE, profile, url=f"{VK_BASE}/{screen_name}"
            )]

        # Fallback: scrape the mobile page
        profile = await self._scrape_profile_page(screen_name)
        return [self.make_result(
            ContentType.PROFILE, profile, url=f"{VK_BASE}/{screen_name}"
        )]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape wall posts from a VK user or community.

        Args:
            source: Username, numeric ID, or full VK URL.
            max_results: Maximum posts to return.
        """
        limit = max_results or self.config.max_results
        screen_name = self._normalize_identifier(source)

        # Try API first
        posts = await self._api_get_wall(screen_name, limit)
        if posts:
            return posts

        # Fallback: scrape the mobile wall page
        return await self._scrape_wall_page(screen_name, limit)

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search VK for content.

        Uses the newsfeed.search API method (works without token for public
        posts) with a web scraping fallback.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Try API search
        results = await self._api_search(query, limit)
        if results:
            return results

        # Fallback: scrape search results page
        return await self._scrape_search_page(query, limit)

    # ------------------------------------------------------------------
    # VK API helpers
    # ------------------------------------------------------------------

    def _api_params(self, **extra) -> dict[str, Any]:
        """Build common API parameters."""
        params: dict[str, Any] = {"v": VK_API_VERSION}
        if self._token:
            params["access_token"] = self._token
        params.update(extra)
        return params

    async def _api_call(self, method: str, **kwargs) -> dict[str, Any] | None:
        """Make a VK API call, returning None on failure."""
        url = f"{VK_API}/{method}"
        params = self._api_params(**kwargs)
        try:
            data = await self.fetch_json(url, params=params)
            if "error" in data:
                error = data["error"]
                logger.debug(
                    "VK API error %s: %s",
                    error.get("error_code"),
                    error.get("error_msg"),
                )
                return None
            return data.get("response")
        except Exception as e:
            logger.debug("VK API call %s failed: %s", method, e)
            return None

    async def _api_get_profile(self, screen_name: str) -> dict[str, Any] | None:
        """Fetch a profile via the VK API (users.get or groups.getById)."""
        # Try as user first
        resp = await self._api_call(
            "users.get",
            user_ids=screen_name,
            fields="photo_max_orig,status,counters,about,city,verified,followers_count",
        )
        if resp and isinstance(resp, list) and resp:
            user = resp[0]
            return {
                "type": "user",
                "user_id": user.get("id"),
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", ""),
                "screen_name": screen_name,
                "photo": user.get("photo_max_orig", ""),
                "status": user.get("status", ""),
                "about": user.get("about", ""),
                "city": user.get("city", {}).get("title", "") if isinstance(user.get("city"), dict) else "",
                "verified": user.get("verified", 0) == 1,
                "followers_count": user.get("followers_count", 0),
                "counters": user.get("counters", {}),
                "url": f"{VK_BASE}/{screen_name}",
            }

        # Try as group/community
        resp = await self._api_call(
            "groups.getById",
            group_id=screen_name,
            fields="description,members_count,status,verified,photo_max_orig",
        )
        if resp and isinstance(resp, list) and resp:
            group = resp[0]
            return {
                "type": "group",
                "group_id": group.get("id"),
                "name": group.get("name", ""),
                "screen_name": group.get("screen_name", screen_name),
                "photo": group.get("photo_max_orig", "") or group.get("photo_200", ""),
                "description": group.get("description", ""),
                "status": group.get("status", ""),
                "members_count": group.get("members_count", 0),
                "verified": group.get("verified", 0) == 1,
                "url": f"{VK_BASE}/{screen_name}",
            }

        return None

    async def _api_get_wall(self, screen_name: str, limit: int) -> list[ScraperResult]:
        """Fetch wall posts via the VK API."""
        # Resolve owner_id from screen_name
        owner_id = await self._resolve_owner_id(screen_name)
        if owner_id is None:
            return []

        results: list[ScraperResult] = []
        offset = 0

        while len(results) < limit:
            count = min(limit - len(results), 100)
            resp = await self._api_call(
                "wall.get",
                owner_id=owner_id,
                count=count,
                offset=offset,
            )
            if not resp or not isinstance(resp, dict):
                break

            items = resp.get("items", [])
            if not items:
                break

            for post in items:
                if len(results) >= limit:
                    break
                post_data = self._normalize_api_post(post, screen_name)
                post_url = f"{VK_BASE}/wall{post.get('owner_id', '')}_{post.get('id', '')}"
                results.append(
                    self.make_result(ContentType.POST, post_data, url=post_url)
                )

            offset += len(items)
            if offset >= resp.get("count", 0):
                break

        return results

    async def _api_search(self, query: str, limit: int) -> list[ScraperResult]:
        """Search via VK API newsfeed.search."""
        results: list[ScraperResult] = []
        start_from = ""

        while len(results) < limit:
            count = min(limit - len(results), 200)
            kwargs: dict[str, Any] = {"q": query, "count": count}
            if start_from:
                kwargs["start_from"] = start_from

            resp = await self._api_call("newsfeed.search", **kwargs)
            if not resp or not isinstance(resp, dict):
                break

            items = resp.get("items", [])
            if not items:
                break

            for post in items:
                if len(results) >= limit:
                    break
                post_data = self._normalize_api_post(post)
                post_url = f"{VK_BASE}/wall{post.get('owner_id', '')}_{post.get('id', '')}"
                results.append(
                    self.make_result(ContentType.SEARCH, post_data, url=post_url)
                )

            start_from = resp.get("next_from", "")
            if not start_from:
                break

        return results

    async def _resolve_owner_id(self, screen_name: str) -> int | None:
        """Resolve a screen_name to a numeric owner_id."""
        # If already numeric
        if screen_name.lstrip("-").isdigit():
            return int(screen_name)

        resp = await self._api_call("utils.resolveScreenName", screen_name=screen_name)
        if not resp or not isinstance(resp, dict):
            return None

        obj_type = resp.get("type")
        obj_id = resp.get("object_id")
        if obj_type == "group":
            return -obj_id  # Groups use negative IDs in wall.get
        return obj_id

    def _normalize_api_post(self, post: dict, screen_name: str = "") -> dict[str, Any]:
        """Normalize a VK API wall post into a standard dict."""
        # Extract attachment info
        attachments: list[dict[str, str]] = []
        for att in post.get("attachments", []):
            att_type = att.get("type", "")
            if att_type == "photo":
                sizes = att.get("photo", {}).get("sizes", [])
                if sizes:
                    # Pick largest
                    best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                    attachments.append({"type": "photo", "url": best.get("url", "")})
            elif att_type == "video":
                video = att.get("video", {})
                attachments.append({
                    "type": "video",
                    "title": video.get("title", ""),
                    "duration": str(video.get("duration", "")),
                    "views": str(video.get("views", 0)),
                })
            elif att_type == "link":
                link = att.get("link", {})
                attachments.append({
                    "type": "link",
                    "url": link.get("url", ""),
                    "title": link.get("title", ""),
                })

        return {
            "post_id": post.get("id"),
            "owner_id": post.get("owner_id"),
            "text": post.get("text", ""),
            "date": post.get("date"),
            "likes": post.get("likes", {}).get("count", 0),
            "reposts": post.get("reposts", {}).get("count", 0),
            "comments": post.get("comments", {}).get("count", 0),
            "views": post.get("views", {}).get("count", 0) if isinstance(post.get("views"), dict) else 0,
            "attachments": attachments,
            "screen_name": screen_name,
            "is_pinned": post.get("is_pinned", 0) == 1,
            "marked_as_ads": post.get("marked_as_ads", 0) == 1,
        }

    # ------------------------------------------------------------------
    # Web scraping fallback
    # ------------------------------------------------------------------

    async def _get_stealth_client(self):
        """Get or create a stealth HTTP client for web scraping."""
        if self._client is None or self._client.is_closed:
            self._client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
        return self._client

    async def _scrape_profile_page(self, screen_name: str) -> dict[str, Any]:
        """Scrape profile from VK's mobile web page."""
        client = await self._get_stealth_client()
        self._throttle()
        url = f"{VK_MOBILE}/{screen_name}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to scrape VK profile page for %s: %s", screen_name, e)
            return {"screen_name": screen_name, "url": f"{VK_BASE}/{screen_name}"}
        self._request_count += 1

        soup = BeautifulSoup(resp.text, "lxml")

        profile: dict[str, Any] = {
            "screen_name": screen_name,
            "url": f"{VK_BASE}/{screen_name}",
            "name": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
        }

        # Extract extra info from page content
        info_rows = soup.find_all(class_=re.compile(r"profile_info|group_info|pp_info", re.IGNORECASE))
        for row in info_rows:
            text = row.get_text(separator=" ", strip=True)
            if "follower" in text.lower() or "subscriber" in text.lower():
                match = re.search(r"([\d,. ]+)", text)
                if match:
                    profile["followers_count"] = int(
                        match.group(1).replace(",", "").replace(".", "").replace(" ", "")
                    )

        return profile

    async def _scrape_wall_page(self, screen_name: str, limit: int) -> list[ScraperResult]:
        """Scrape wall posts from VK's mobile web page."""
        client = await self._get_stealth_client()
        self._throttle()

        url = f"{VK_MOBILE}/{screen_name}?own=1"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to scrape VK wall for %s: %s", screen_name, e)
            return []
        self._request_count += 1

        soup = BeautifulSoup(resp.text, "lxml")
        results: list[ScraperResult] = []

        for wall_item in soup.find_all(class_=re.compile(r"wall_item|post", re.IGNORECASE)):
            if len(results) >= limit:
                break

            # Post text
            text_el = wall_item.find(class_=re.compile(r"pi_text|wall_post_text|post_body", re.IGNORECASE))
            text = text_el.get_text(separator="\n", strip=True) if text_el else ""

            # Post link
            link = wall_item.find("a", href=re.compile(r"/wall-?\d+_\d+"))
            post_url = ""
            if link:
                href = link["href"]
                post_url = href if href.startswith("http") else f"{VK_BASE}{href}"

            # Date
            date_el = wall_item.find("time") or wall_item.find(class_=re.compile(r"wi_date|post_date", re.IGNORECASE))
            date = ""
            if date_el:
                date = date_el.get("datetime", date_el.get_text(strip=True))

            # Likes
            likes = 0
            like_el = wall_item.find(class_=re.compile(r"like|heart", re.IGNORECASE))
            if like_el:
                match = re.search(r"(\d+)", like_el.get_text())
                if match:
                    likes = int(match.group(1))

            # Images
            images = [
                img["src"]
                for img in wall_item.find_all("img", src=True)
                if "emoji" not in img.get("src", "") and "avatar" not in img.get("class", [])
            ]

            post_data = {
                "text": text,
                "date": date,
                "likes": likes,
                "images": images,
                "url": post_url,
                "screen_name": screen_name,
            }
            results.append(
                self.make_result(ContentType.POST, post_data, url=post_url)
            )

        return results

    async def _scrape_search_page(self, query: str, limit: int) -> list[ScraperResult]:
        """Scrape search results from VK's mobile web search."""
        client = await self._get_stealth_client()
        self._throttle()

        url = f"{VK_MOBILE}/search?c[q]={quote(query)}&c[section]=auto"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to scrape VK search for '%s': %s", query, e)
            return []
        self._request_count += 1

        soup = BeautifulSoup(resp.text, "lxml")
        results: list[ScraperResult] = []

        for item in soup.find_all(class_=re.compile(r"search_row|result|wall_item", re.IGNORECASE)):
            if len(results) >= limit:
                break

            link = item.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if not href.startswith("http"):
                href = f"{VK_BASE}{href}"

            title_el = item.find(["h4", "h3", "span"], class_=re.compile(r"title|name", re.IGNORECASE))
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            text_el = item.find(class_=re.compile(r"text|description|body", re.IGNORECASE))
            preview = text_el.get_text(strip=True)[:300] if text_el else ""

            img = item.find("img", src=True)
            image = img["src"] if img else ""

            entry = {
                "title": title,
                "preview": preview,
                "url": href,
                "image": image,
            }
            results.append(
                self.make_result(ContentType.SEARCH, entry, url=href)
            )

        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        """Extract screen_name from a URL or bare identifier."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            # Remove known prefixes like "id123456" stays as-is
            parts = path.split("/")
            return parts[0] if parts else identifier
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
