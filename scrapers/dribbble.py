"""Dribbble scraper using stealth web scraping.

No API key required. Scrapes public designer profiles, shots, and search
results from the Dribbble website using stealth HTTP headers to avoid
bot detection.
Supports: designer profiles, shots, search.
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

DRIBBBLE_BASE = "https://dribbble.com"


class DribbbleScraper(BaseScraper):
    """Dribbble scraper using stealth web scraping.

    No authentication needed. Uses stealth HTTP sessions with realistic
    browser fingerprints to scrape public Dribbble pages.

    Usage:
        scraper = DribbbleScraper()
        results = await scraper.scrape_profile("simplebits")
        results = await scraper.scrape_posts("simplebits", max_results=20)
        results = await scraper.search("mobile app design", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "dribbble"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Dribbble designer profile.

        Args:
            identifier: Username or full profile URL.
        """
        username = self._normalize_username(identifier)
        url = f"{DRIBBBLE_BASE}/{username}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            profile = self._extract_profile(soup, username)
            profile["url"] = url

            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await client.aclose()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape shots from a designer's profile.

        Args:
            source: Username, profile URL, or 'popular'/'recent' for
                    global feeds.
            max_results: Maximum shots to return.
        """
        limit = max_results or self.config.max_results

        # Determine the shots listing URL
        if source.lower() in ("popular", "trending"):
            url = f"{DRIBBBLE_BASE}/shots/popular"
        elif source.lower() == "recent":
            url = f"{DRIBBBLE_BASE}/shots/recent"
        elif source.lower() == "following":
            url = f"{DRIBBBLE_BASE}/shots/following"
        elif source.startswith("http"):
            url = source
        else:
            username = self._normalize_username(source)
            url = f"{DRIBBBLE_BASE}/{username}/shots"

        results: list[ScraperResult] = []
        page = 1

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            while len(results) < limit:
                page_url = f"{url}?page={page}" if page > 1 else url
                resp = await client.get(page_url, follow_redirects=True)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                shots = self._extract_shots(soup, limit - len(results))

                if not shots:
                    break

                for shot in shots:
                    if len(results) >= limit:
                        break
                    results.append(
                        self.make_result(
                            ContentType.IMAGE, shot, url=shot.get("url", "")
                        )
                    )

                # Check if there is a next page
                if not self._has_next_page(soup):
                    break

                page += 1
        finally:
            await client.aclose()

        return results

    async def scrape_shot(self, shot_url: str) -> list[ScraperResult]:
        """Scrape detailed data for a single shot.

        Args:
            shot_url: Full URL to the shot page.
        """
        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(shot_url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            shot = self._extract_shot_detail(soup, shot_url)

            return [self.make_result(ContentType.IMAGE, shot, url=shot_url)]
        finally:
            await client.aclose()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Dribbble for shots.

        Args:
            query: Search query string.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        results: list[ScraperResult] = []
        page = 1

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            while len(results) < limit:
                search_url = (
                    f"{DRIBBBLE_BASE}/search/shots/{quote_plus(query)}"
                    f"?page={page}"
                )
                resp = await client.get(search_url, follow_redirects=True)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                shots = self._extract_shots(soup, limit - len(results))

                if not shots:
                    break

                for shot in shots:
                    if len(results) >= limit:
                        break
                    results.append(
                        self.make_result(
                            ContentType.SEARCH, shot, url=shot.get("url", "")
                        )
                    )

                if not self._has_next_page(soup):
                    break

                page += 1
        finally:
            await client.aclose()

        return results

    async def search_designers(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search for designers on Dribbble.

        Args:
            query: Search query for designers.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        search_url = f"{DRIBBBLE_BASE}/search/users/{quote_plus(query)}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(search_url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results: list[ScraperResult] = []
            for card in soup.find_all(
                ["li", "div"], class_=re.compile(r"user|designer|member|result")
            ):
                if len(results) >= limit:
                    break

                link = card.find("a", href=re.compile(r"^/[a-zA-Z0-9_-]+$"))
                if not link:
                    continue

                username = link["href"].strip("/")
                name_el = card.find(["h3", "h2", "strong", "span"])
                name = name_el.get_text(strip=True) if name_el else username

                avatar = ""
                img = card.find("img")
                if img:
                    avatar = img.get("src", "") or img.get("data-src", "")

                location_el = card.find(
                    class_=re.compile(r"location|loc")
                )
                location = (
                    location_el.get_text(strip=True) if location_el else ""
                )

                designer = {
                    "username": username,
                    "name": name,
                    "avatar": avatar,
                    "location": location,
                    "url": f"{DRIBBBLE_BASE}/{username}",
                }
                results.append(
                    self.make_result(
                        ContentType.PROFILE, designer, url=designer["url"]
                    )
                )

            return results
        finally:
            await client.aclose()

    # --- Extraction helpers ---

    def _extract_profile(self, soup: BeautifulSoup, username: str) -> dict:
        """Extract designer profile data from the profile page."""
        # Try JSON-LD structured data
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            if script.string:
                try:
                    ld = json.loads(script.string)
                    if isinstance(ld, dict) and ld.get("@type") in (
                        "Person",
                        "ProfilePage",
                    ):
                        return {
                            "username": username,
                            "name": ld.get("name", username),
                            "bio": ld.get("description", ""),
                            "avatar": ld.get("image", ""),
                            "url": ld.get("url", f"{DRIBBBLE_BASE}/{username}"),
                        }
                except json.JSONDecodeError:
                    continue

        # Parse from page structure
        name = self._meta(soup, "og:title") or username
        # Remove " - Dribbble" suffix from title
        name = re.sub(r"\s*[-|]\s*Dribbble.*$", "", name).strip()

        bio_el = soup.find(class_=re.compile(r"bio|about"))
        bio = bio_el.get_text(strip=True) if bio_el else ""

        if not bio:
            bio = self._meta(soup, "og:description") or ""
            bio = re.sub(r"\s*on Dribbble.*$", "", bio).strip()

        avatar = self._meta(soup, "og:image") or ""

        # Extract stats
        stats = self._extract_stats(soup)

        location_el = soup.find(class_=re.compile(r"location"))
        location = location_el.get_text(strip=True) if location_el else ""

        # Look for skills/specialties
        skills: list[str] = []
        for badge in soup.find_all(class_=re.compile(r"skill|badge|tag|specialty")):
            text = badge.get_text(strip=True)
            if text and len(text) < 50:
                skills.append(text)

        return {
            "username": username,
            "name": name,
            "bio": bio,
            "avatar": avatar,
            "location": location,
            "shots_count": stats.get("shots", 0),
            "followers_count": stats.get("followers", 0),
            "following_count": stats.get("following", 0),
            "likes_count": stats.get("likes", 0),
            "skills": skills[:20],
        }

    def _extract_shots(self, soup: BeautifulSoup, limit: int) -> list[dict]:
        """Extract shot data from a listing page."""
        shots: list[dict] = []
        seen: set[str] = set()

        # Look for shot cards in the page
        # Dribbble uses <li> elements with shot data or <div> shot containers
        for item in soup.find_all(
            ["li", "div", "article"],
            class_=re.compile(r"shot|dribbble|group|js-shot"),
            limit=limit * 2,
        ):
            shot = self._parse_shot_card(item, seen)
            if shot:
                shots.append(shot)
                if len(shots) >= limit:
                    break

        # Fallback: find shot links directly
        if not shots:
            for link in soup.find_all("a", href=re.compile(r"/shots/\d+")):
                href = link["href"]
                shot_id = re.search(r"/shots/(\d+)", href)
                if not shot_id:
                    continue
                sid = shot_id.group(1)
                if sid in seen:
                    continue
                seen.add(sid)

                img = link.find("img")
                title = ""
                image_url = ""
                if img:
                    title = img.get("alt", "")
                    image_url = (
                        img.get("src", "")
                        or img.get("data-src", "")
                        or img.get("srcset", "").split(",")[0].split(" ")[0]
                    )

                shots.append({
                    "shot_id": sid,
                    "title": title,
                    "image": image_url,
                    "url": f"{DRIBBBLE_BASE}/shots/{sid}",
                })
                if len(shots) >= limit:
                    break

        return shots

    def _parse_shot_card(self, element: Any, seen: set[str]) -> dict | None:
        """Parse a single shot card element."""
        # Find the shot link
        link = element.find("a", href=re.compile(r"/shots/\d+"))
        if not link:
            return None

        href = link["href"]
        match = re.search(r"/shots/(\d+)", href)
        if not match:
            return None

        shot_id = match.group(1)
        if shot_id in seen:
            return None
        seen.add(shot_id)

        # Extract the slug from the URL for a nicer URL
        full_url = href if href.startswith("http") else f"{DRIBBBLE_BASE}{href}"

        # Get image
        img = element.find("img")
        image_url = ""
        title = ""
        if img:
            title = img.get("alt", "")
            image_url = (
                img.get("src", "")
                or img.get("data-src", "")
                or img.get("srcset", "").split(",")[0].split(" ")[0]
            )

        # Get designer info
        designer_link = element.find(
            "a", href=re.compile(r"^/[a-zA-Z0-9_-]+$")
        )
        designer = ""
        if designer_link:
            designer = designer_link.get_text(strip=True)

        # Get likes/views from data attributes or text
        likes = self._parse_count(element, r"like|heart|fav")
        views = self._parse_count(element, r"view|eye")

        return {
            "shot_id": shot_id,
            "title": title,
            "image": image_url,
            "url": full_url,
            "designer": designer,
            "likes_count": likes,
            "views_count": views,
        }

    def _extract_shot_detail(self, soup: BeautifulSoup, shot_url: str) -> dict:
        """Extract detailed data from a single shot page."""
        title = self._meta(soup, "og:title") or ""
        title = re.sub(r"\s*[-|]\s*Dribbble.*$", "", title).strip()

        description = self._meta(soup, "og:description") or ""
        image = self._meta(soup, "og:image") or ""

        # Find shot ID from URL
        shot_id = ""
        match = re.search(r"/shots/(\d+)", shot_url)
        if match:
            shot_id = match.group(1)

        # Extract detailed content
        content_el = soup.find(
            class_=re.compile(r"shot-desc|description|shot-content")
        )
        content = content_el.get_text(separator="\n", strip=True) if content_el else ""

        # Extract tags
        tags: list[str] = []
        for tag_link in soup.find_all("a", href=re.compile(r"/tags/")):
            tag_text = tag_link.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        # Extract color palette
        colors: list[str] = []
        for color_el in soup.find_all(
            class_=re.compile(r"color"), attrs={"style": re.compile(r"background")}
        ):
            style = color_el.get("style", "")
            hex_match = re.search(r"#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})", style)
            if hex_match:
                colors.append(f"#{hex_match.group(1)}")

        # Extract designer
        designer_el = soup.find(class_=re.compile(r"shot-byline|user-info|shot-user"))
        designer = ""
        if designer_el:
            link = designer_el.find("a")
            designer = link.get_text(strip=True) if link else ""

        # Get stats
        stats = self._extract_stats(soup)

        return {
            "shot_id": shot_id,
            "title": title,
            "description": description,
            "content": content[:3000],
            "image": image,
            "url": shot_url,
            "designer": designer,
            "tags": tags,
            "colors": colors,
            "likes_count": stats.get("likes", 0),
            "views_count": stats.get("views", 0),
            "saves_count": stats.get("saves", 0),
        }

    def _extract_stats(self, soup: BeautifulSoup) -> dict[str, int]:
        """Extract numeric stats from a page."""
        stats: dict[str, int] = {}
        for stat_el in soup.find_all(
            class_=re.compile(r"stat|count|metric"), limit=20
        ):
            text = stat_el.get_text(strip=True).lower()
            value = self._parse_numeric(text)
            if value <= 0:
                continue

            if "shot" in text:
                stats["shots"] = value
            elif "follower" in text:
                stats["followers"] = value
            elif "following" in text:
                stats["following"] = value
            elif "like" in text or "heart" in text:
                stats["likes"] = value
            elif "view" in text:
                stats["views"] = value
            elif "save" in text or "bucket" in text:
                stats["saves"] = value

        return stats

    @staticmethod
    def _parse_count(element: Any, pattern: str) -> int:
        """Find and parse a count value from an element by pattern."""
        el = element.find(class_=re.compile(pattern))
        if not el:
            return 0
        text = el.get_text(strip=True)
        return DribbbleScraper._parse_numeric(text)

    @staticmethod
    def _parse_numeric(text: str) -> int:
        """Parse a human-readable number (e.g. '1.2k', '500')."""
        text = text.strip().replace(",", "")
        match = re.search(r"([\d.]+)\s*([kKmM])?", text)
        if not match:
            return 0
        num = float(match.group(1))
        suffix = (match.group(2) or "").lower()
        if suffix == "k":
            return int(num * 1000)
        if suffix == "m":
            return int(num * 1_000_000)
        return int(num)

    @staticmethod
    def _has_next_page(soup: BeautifulSoup) -> bool:
        """Check if the page has a next-page link."""
        next_link = soup.find("a", {"rel": "next"})
        if next_link:
            return True
        # Also check for pagination elements
        pag = soup.find(class_=re.compile(r"pagination|pager"))
        if pag:
            next_el = pag.find("a", class_=re.compile(r"next"))
            return next_el is not None
        return False

    def _normalize_username(self, identifier: str) -> str:
        """Normalize an identifier to a Dribbble username."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            return path.split("/")[0]
        return identifier.strip("/").strip("@")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return tag.get("content", "") if tag else ""
