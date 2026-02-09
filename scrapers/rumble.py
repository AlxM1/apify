"""Rumble video platform scraper using stealth web scraping.

No API key required. Rumble does not expose a public API, so data is extracted
by scraping HTML pages with stealth browser headers and parsing embedded JSON
data (ld+json, __NEXT_DATA__, inline script variables) from page source.

Supports: channel profiles, videos, search.
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

RUMBLE_BASE = "https://rumble.com"


class RumbleScraper(BaseScraper):
    """Rumble scraper using stealth HTTP requests and embedded JSON extraction.

    Uses StealthSession for realistic browser fingerprints to avoid bot
    detection. Extracts structured data from JSON-LD, inline script
    variables, and HTML elements.

    Usage:
        scraper = RumbleScraper()
        results = await scraper.scrape_profile("Bongino")
        results = await scraper.scrape_posts("Bongino", max_results=20)
        results = await scraper.search("news", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "rumble"

    async def get_client(self):
        """Override to use stealth headers."""
        if self._client is None or self._client.is_closed:
            self._client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Rumble channel profile.

        Args:
            identifier: Channel name/slug (e.g. "Bongino") or full URL.
        """
        slug = self._normalize_channel(identifier)
        url = f"{RUMBLE_BASE}/c/{slug}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try JSON-LD first
        profile = self._extract_jsonld_profile(soup)

        if not profile:
            # Fallback to HTML/meta extraction
            profile = {
                "channel_name": self._meta(soup, "og:title") or slug,
                "description": self._meta(soup, "og:description") or "",
                "image": self._meta(soup, "og:image") or "",
            }

        profile["slug"] = slug
        profile["url"] = url

        # Extract follower/subscriber count from page text
        for el in soup.find_all(string=re.compile(r"[\d,.]+[KMB]?\s*(follower|subscriber)", re.IGNORECASE)):
            match = re.search(r"([\d,.]+[KMB]?)\s*(follower|subscriber)", str(el), re.IGNORECASE)
            if match:
                profile["follower_count"] = self._parse_count(match.group(1))
                break

        # Extract video count from page text
        for el in soup.find_all(string=re.compile(r"[\d,.]+\s*video", re.IGNORECASE)):
            match = re.search(r"([\d,.]+)\s*video", str(el), re.IGNORECASE)
            if match:
                profile["video_count"] = int(match.group(1).replace(",", ""))
                break

        # Check if currently live
        live_el = soup.find(class_=re.compile(r"live-indicator|is-live", re.IGNORECASE))
        profile["is_live"] = live_el is not None

        return [self.make_result(ContentType.PROFILE, profile, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape videos from a Rumble channel.

        Paginates through the channel's video listing pages.

        Args:
            source: Channel name/slug or URL.
            max_results: Maximum number of videos to fetch.
        """
        limit = max_results or self.config.max_results
        slug = self._normalize_channel(source)

        results: list[ScraperResult] = []
        page_num = 1

        while len(results) < limit:
            if page_num == 1:
                url = f"{RUMBLE_BASE}/c/{slug}"
            else:
                url = f"{RUMBLE_BASE}/c/{slug}?page={page_num}"

            resp = await self.fetch(url)
            soup = BeautifulSoup(resp.text, "lxml")

            # Extract videos from JSON-LD
            page_videos = self._extract_jsonld_videos(soup)

            # Fallback to HTML parsing
            if not page_videos:
                page_videos = self._extract_html_videos(soup, slug)

            if not page_videos:
                break

            for video in page_videos:
                if len(results) >= limit:
                    break
                results.append(
                    self.make_result(ContentType.VIDEO, video, url=video.get("url", ""))
                )

            # Check if there is a next page
            next_link = soup.find("a", class_=re.compile(r"paginator.*next|next-page", re.IGNORECASE))
            if not next_link:
                # Also check for simple "next" text link
                next_link = soup.find("a", string=re.compile(r"next", re.IGNORECASE))
            if not next_link or len(results) >= limit:
                break

            page_num += 1

        return results

    async def scrape_video(self, video_url: str) -> list[ScraperResult]:
        """Scrape metadata for a single Rumble video.

        Args:
            video_url: Full URL to the Rumble video page.
        """
        resp = await self.fetch(video_url)
        soup = BeautifulSoup(resp.text, "lxml")

        video = self._extract_video_detail(soup, video_url)
        return [self.make_result(ContentType.VIDEO, video, url=video_url)]

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Rumble for videos.

        Args:
            query: Search query string.
            max_results: Maximum number of results.
        """
        limit = max_results or self.config.max_results
        results: list[ScraperResult] = []
        page_num = 1

        while len(results) < limit:
            search_url = f"{RUMBLE_BASE}/search/video?q={quote(query)}"
            if page_num > 1:
                search_url += f"&page={page_num}"

            resp = await self.fetch(search_url)
            soup = BeautifulSoup(resp.text, "lxml")

            page_videos = self._extract_search_results(soup)
            if not page_videos:
                break

            for video in page_videos:
                if len(results) >= limit:
                    break
                results.append(
                    self.make_result(ContentType.SEARCH, video, url=video.get("url", ""))
                )

            # Check for next page
            next_link = soup.find("a", class_=re.compile(r"paginator.*next|next-page", re.IGNORECASE))
            if not next_link:
                next_link = soup.find("a", string=re.compile(r"next", re.IGNORECASE))
            if not next_link or len(results) >= limit:
                break

            page_num += 1

        return results

    # ------------------------------------------------------------------
    # JSON-LD extraction
    # ------------------------------------------------------------------

    def _extract_jsonld_profile(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Extract channel profile from JSON-LD scripts."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            # May be a list of objects
            items = data if isinstance(data, list) else [data]
            for item in items:
                item_type = item.get("@type", "")
                if item_type in ("Person", "Organization", "BroadcastChannel", "WebPage"):
                    return {
                        "channel_name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "image": (
                            item.get("image", {}).get("url", "")
                            if isinstance(item.get("image"), dict)
                            else item.get("image", "")
                        ),
                    }
        return {}

    def _extract_jsonld_videos(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Extract video items from JSON-LD scripts on a listing page."""
        videos: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "ItemList":
                    for elem in item.get("itemListElement", []):
                        video_item = elem.get("item", elem)
                        videos.append(self._normalize_jsonld_video(video_item))
                elif item.get("@type") == "VideoObject":
                    videos.append(self._normalize_jsonld_video(item))

        return videos

    def _normalize_jsonld_video(self, item: dict) -> dict[str, Any]:
        """Normalize a JSON-LD VideoObject into our standard format."""
        thumbnail = item.get("thumbnailUrl", "")
        if isinstance(thumbnail, list):
            thumbnail = thumbnail[0] if thumbnail else ""

        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = f"{RUMBLE_BASE}{url}"

        return {
            "title": item.get("name", ""),
            "description": (item.get("description", "") or "")[:500],
            "url": url,
            "thumbnail": thumbnail,
            "duration": item.get("duration", ""),
            "upload_date": item.get("uploadDate", "") or item.get("datePublished", ""),
            "view_count": self._extract_interaction_count(item, "WatchAction"),
            "like_count": self._extract_interaction_count(item, "LikeAction"),
            "channel_name": (
                item.get("author", {}).get("name", "")
                if isinstance(item.get("author"), dict) else ""
            ),
        }

    @staticmethod
    def _extract_interaction_count(item: dict, action_type: str) -> int:
        """Pull a specific interaction count from JSON-LD interactionStatistic."""
        for stat in item.get("interactionStatistic", []):
            if not isinstance(stat, dict):
                continue
            interaction = stat.get("interactionType", "")
            if isinstance(interaction, dict):
                interaction = interaction.get("@type", "")
            if action_type in str(interaction):
                try:
                    return int(stat.get("userInteractionCount", 0))
                except (ValueError, TypeError):
                    pass
        return 0

    # ------------------------------------------------------------------
    # HTML fallback extraction
    # ------------------------------------------------------------------

    def _extract_html_videos(self, soup: BeautifulSoup, slug: str) -> list[dict[str, Any]]:
        """Parse video cards from HTML when JSON-LD is unavailable."""
        videos: list[dict[str, Any]] = []

        # Rumble uses various class patterns for video listings
        for card in soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"video-item|videostream|thumbnail__grid", re.IGNORECASE),
        ):
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if not href.startswith("http"):
                href = f"{RUMBLE_BASE}{href}"

            title_el = card.find(["h3", "h4", "span"], class_=re.compile(r"title", re.IGNORECASE))
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            # Thumbnail
            img = card.find("img", src=True)
            thumbnail = img["src"] if img else ""

            # View count
            views_el = card.find(class_=re.compile(r"view|rumble", re.IGNORECASE))
            views = 0
            if views_el:
                match = re.search(r"([\d,.]+[KMB]?)", views_el.get_text())
                if match:
                    views = self._parse_count(match.group(1))

            # Duration
            duration_el = card.find(class_=re.compile(r"duration|length", re.IGNORECASE))
            duration = duration_el.get_text(strip=True) if duration_el else ""

            # Date
            date_el = card.find("time") or card.find(class_=re.compile(r"date|time", re.IGNORECASE))
            date = ""
            if date_el:
                date = date_el.get("datetime", date_el.get_text(strip=True))

            videos.append({
                "title": title,
                "url": href,
                "thumbnail": thumbnail,
                "view_count": views,
                "duration": duration,
                "upload_date": date,
                "channel_name": slug,
            })

        return videos

    def _extract_search_results(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse video results from a Rumble search page."""
        results: list[dict[str, Any]] = []

        # Try JSON-LD first (some search pages include it)
        jsonld_videos = self._extract_jsonld_videos(soup)
        if jsonld_videos:
            return jsonld_videos

        # Fallback to HTML parsing of search result cards
        for card in soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"video-item|videostream|search-result|thumbnail", re.IGNORECASE),
        ):
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if not href.startswith("http"):
                href = f"{RUMBLE_BASE}{href}"

            title_el = card.find(["h3", "h4", "span"], class_=re.compile(r"title", re.IGNORECASE))
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 2:
                continue

            img = card.find("img", src=True)
            thumbnail = img["src"] if img else ""

            # Channel/author
            author_el = card.find(class_=re.compile(r"author|channel|user", re.IGNORECASE))
            author = author_el.get_text(strip=True) if author_el else ""

            # Views
            views = 0
            views_el = card.find(class_=re.compile(r"view|rumble", re.IGNORECASE))
            if views_el:
                match = re.search(r"([\d,.]+[KMB]?)", views_el.get_text())
                if match:
                    views = self._parse_count(match.group(1))

            # Date
            date_el = card.find("time") or card.find(class_=re.compile(r"date|time", re.IGNORECASE))
            date = ""
            if date_el:
                date = date_el.get("datetime", date_el.get_text(strip=True))

            results.append({
                "title": title,
                "url": href,
                "thumbnail": thumbnail,
                "channel_name": author,
                "view_count": views,
                "upload_date": date,
            })

        return results

    def _extract_video_detail(self, soup: BeautifulSoup, url: str) -> dict[str, Any]:
        """Extract full metadata from a single video page."""
        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "VideoObject":
                    video = self._normalize_jsonld_video(item)
                    video["url"] = url
                    return video

        # Try extracting embedded JSON from script tags
        for script in soup.find_all("script"):
            if not script.string:
                continue
            # Rumble often inlines video config as a JS object
            match = re.search(r'(?:videoConfig|mediaConfig)\s*=\s*(\{.*?\});', script.string, re.DOTALL)
            if match:
                try:
                    config_data = json.loads(match.group(1))
                    return {
                        "title": config_data.get("title", ""),
                        "description": config_data.get("description", "")[:500],
                        "url": url,
                        "duration": config_data.get("duration", ""),
                        "thumbnail": config_data.get("thumbnail", ""),
                        "author": config_data.get("author", {}).get("name", ""),
                    }
                except json.JSONDecodeError:
                    continue

        # Final fallback to meta tags
        return {
            "title": self._meta(soup, "og:title") or "",
            "description": (self._meta(soup, "og:description") or "")[:500],
            "url": url,
            "thumbnail": self._meta(soup, "og:image") or "",
            "duration": self._meta(soup, "video:duration") or "",
            "upload_date": self._meta(soup, "article:published_time") or "",
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_channel(identifier: str) -> str:
        """Extract channel slug from a URL or bare name."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            # /c/ChannelName or /user/ChannelName
            parts = path.split("/")
            if len(parts) >= 2 and parts[0] in ("c", "user"):
                return parts[1]
            return parts[-1] if parts else identifier
        return identifier.strip().strip("/")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        if tag:
            return tag.get("content", "")
        return ""

    @staticmethod
    def _parse_count(text: str) -> int:
        """Parse human-readable counts like '1.2K', '3.4M', '500'."""
        text = text.strip().replace(",", "")
        multiplier = 1
        if text.endswith("K"):
            multiplier = 1_000
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1_000_000
            text = text[:-1]
        elif text.endswith("B"):
            multiplier = 1_000_000_000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0
