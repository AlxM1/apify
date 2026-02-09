"""Pinterest scraper using web scraping.

No API key required. Scrapes public pins, boards, and profiles.
Supports: profiles, pins, boards, search.
"""

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

PINTEREST_BASE = "https://www.pinterest.com"


class PinterestScraper(BaseScraper):
    """Pinterest scraper using web scraping and resource endpoint.

    Usage:
        scraper = PinterestScraper()
        results = await scraper.scrape_profile("pinterest")
        results = await scraper.scrape_posts("pinterest", max_results=20)
        results = await scraper.search("home decor", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "pinterest"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Pinterest user profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        url = f"{PINTEREST_BASE}/{username}/"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Extract from initial state JSON
            profile = self._extract_profile_from_page(soup, username)
            profile["url"] = url

            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await client.aclose()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape pins from a user profile or board.

        Args:
            source: Username, board URL, or profile URL.
            max_results: Maximum pins to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)

        # Use the resource API to get pins
        pins = await self._fetch_user_pins(username, limit)

        results = []
        for pin in pins[:limit]:
            results.append(
                self.make_result(ContentType.IMAGE, pin, url=pin.get("url", ""))
            )

        return results

    async def scrape_board(
        self, board_url: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape pins from a specific board.

        Args:
            board_url: Board URL (e.g. pinterest.com/user/board-name/).
            max_results: Maximum pins.
        """
        limit = max_results or self.config.max_results

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(board_url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            pins = self._extract_pins_from_page(soup, limit)

            results = []
            for pin in pins[:limit]:
                results.append(
                    self.make_result(ContentType.IMAGE, pin, url=pin.get("url", ""))
                )

            return results
        finally:
            await client.aclose()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Pinterest.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        search_url = f"{PINTEREST_BASE}/search/pins/?q={query}&rs=typed"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(search_url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            pins = self._extract_pins_from_page(soup, limit)

            results = []
            for pin in pins[:limit]:
                results.append(
                    self.make_result(ContentType.SEARCH, pin, url=pin.get("url", ""))
                )

            return results
        finally:
            await client.aclose()

    async def _fetch_user_pins(self, username: str, limit: int) -> list[dict]:
        """Fetch pins using Pinterest's resource endpoint."""
        url = f"{PINTEREST_BASE}/{username}/pins/"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            return self._extract_pins_from_page(soup, limit)
        finally:
            await client.aclose()

    def _extract_profile_from_page(self, soup: BeautifulSoup, username: str) -> dict:
        """Extract profile data from page HTML / embedded JSON."""
        # Try to find initial data script
        for script in soup.find_all("script", {"type": "application/json"}):
            if script.string:
                try:
                    data = json.loads(script.string)
                    profile = self._find_profile_in_data(data, username)
                    if profile:
                        return profile
                except json.JSONDecodeError:
                    continue

        # Try __PWS_DATA__
        for script in soup.find_all("script", {"id": "__PWS_DATA__"}):
            if script.string:
                try:
                    data = json.loads(script.string)
                    profile = self._find_profile_in_data(data, username)
                    if profile:
                        return profile
                except json.JSONDecodeError:
                    pass

        # Fallback to meta tags
        return {
            "username": username,
            "name": self._meta(soup, "og:title") or username,
            "description": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
        }

    def _find_profile_in_data(self, data: Any, username: str) -> dict | None:
        if isinstance(data, dict):
            if data.get("username") == username or data.get("type") == "user":
                return {
                    "username": data.get("username", username),
                    "name": data.get("full_name", "") or data.get("first_name", ""),
                    "bio": data.get("about", "") or data.get("bio", ""),
                    "follower_count": data.get("follower_count", 0),
                    "following_count": data.get("following_count", 0),
                    "pin_count": data.get("pin_count", 0),
                    "board_count": data.get("board_count", 0),
                    "image": data.get("image_xlarge_url", "") or data.get("profile_image", ""),
                    "verified": data.get("is_verified_merchant", False),
                    "website": data.get("website_url", ""),
                    "location": data.get("location", ""),
                }
            for v in data.values():
                result = self._find_profile_in_data(v, username)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_profile_in_data(item, username)
                if result:
                    return result
        return None

    def _extract_pins_from_page(self, soup: BeautifulSoup, limit: int) -> list[dict]:
        """Extract pin data from page HTML."""
        pins = []
        seen = set()

        # Try to find pin data in embedded JSON
        for script in soup.find_all("script", {"type": "application/json"}):
            if script.string and len(pins) < limit:
                try:
                    data = json.loads(script.string)
                    self._find_pins_in_data(data, pins, limit, seen)
                except json.JSONDecodeError:
                    continue

        # Try __PWS_DATA__
        for script in soup.find_all("script", {"id": "__PWS_DATA__"}):
            if script.string and len(pins) < limit:
                try:
                    data = json.loads(script.string)
                    self._find_pins_in_data(data, pins, limit, seen)
                except json.JSONDecodeError:
                    pass

        # Fallback: extract from links
        if not pins:
            for link in soup.find_all("a", href=re.compile(r"/pin/\d+")):
                pin_id = link["href"].split("/pin/")[-1].strip("/").split("/")[0]
                if pin_id in seen:
                    continue
                seen.add(pin_id)
                img = link.find("img")
                pins.append({
                    "pin_id": pin_id,
                    "url": f"{PINTEREST_BASE}/pin/{pin_id}/",
                    "image": img.get("src", "") if img else "",
                    "alt_text": img.get("alt", "") if img else "",
                })
                if len(pins) >= limit:
                    break

        return pins

    def _find_pins_in_data(
        self, data: Any, pins: list[dict], limit: int, seen: set
    ):
        if len(pins) >= limit:
            return
        if isinstance(data, dict):
            pin_id = data.get("id")
            if pin_id and data.get("type") == "pin" and str(pin_id) not in seen:
                seen.add(str(pin_id))
                pin = {
                    "pin_id": str(pin_id),
                    "title": data.get("title", "") or data.get("grid_title", ""),
                    "description": data.get("description", ""),
                    "url": f"{PINTEREST_BASE}/pin/{pin_id}/",
                    "image": (data.get("images", {}).get("orig", {}).get("url", "")
                              or data.get("image_large_url", "")),
                    "link": data.get("link", ""),
                    "dominant_color": data.get("dominant_color", ""),
                    "save_count": data.get("aggregated_pin_data", {}).get("aggregated_stats", {}).get("saves", 0),
                    "comment_count": data.get("comment_count", 0),
                    "pinner": data.get("pinner", {}).get("username", ""),
                    "board_name": data.get("board", {}).get("name", ""),
                }
                pins.append(pin)

            for v in data.values():
                self._find_pins_in_data(v, pins, limit, seen)
        elif isinstance(data, list):
            for item in data:
                self._find_pins_in_data(item, pins, limit, seen)

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            from urllib.parse import urlparse
            path = urlparse(identifier).path.strip("/")
            return path.split("/")[0]
        return identifier.strip("/").strip("@")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
