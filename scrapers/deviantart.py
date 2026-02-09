"""DeviantArt scraper using web scraping and RSS feeds.

No API key required. Uses DeviantArt's public RSS feed at
backend.deviantart.com/rss.xml for content discovery and HTML parsing
for profiles and full deviation details.
Supports: artist profiles, deviations, galleries, search.
"""

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

DEVIANTART_BASE = "https://www.deviantart.com"
DEVIANTART_RSS = "https://backend.deviantart.com/rss.xml"

# XML namespace map for DeviantArt's RSS extensions
_NS = {
    "media": "http://search.yahoo.com/mrss/",
    "atom": "http://www.w3.org/2005/Atom",
    "creativeCommons": "http://backend.userland.com/creativeCommonsRssModule",
}


class DeviantArtScraper(BaseScraper):
    """DeviantArt scraper using RSS feeds and web scraping.

    No authentication needed. Uses DeviantArt's RSS endpoint for deviation
    discovery and page scraping for profiles and detailed deviation data.

    Usage:
        scraper = DeviantArtScraper()
        results = await scraper.scrape_profile("yuumei")
        results = await scraper.scrape_posts("yuumei", max_results=20)
        results = await scraper.search("digital painting landscape", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "deviantart"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a DeviantArt artist profile.

        Args:
            identifier: Username or full profile URL.
        """
        username = self._normalize_username(identifier)
        url = f"{DEVIANTART_BASE}/{username}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        profile = self._extract_profile(soup, username)
        profile["url"] = url

        return [self.make_result(ContentType.PROFILE, profile, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape deviations from an artist's gallery via RSS.

        Args:
            source: Username, gallery URL, or 'popular'/'newest' for global
                    feeds.
            max_results: Maximum deviations to return.
        """
        limit = max_results or self.config.max_results

        if source.lower() in ("popular", "hot"):
            rss_url = f"{DEVIANTART_RSS}?type=deviation&order=popular"
        elif source.lower() in ("newest", "recent", "new"):
            rss_url = f"{DEVIANTART_RSS}?type=deviation&order=newest"
        elif source.startswith("http"):
            username = self._normalize_username(source)
            rss_url = f"{DEVIANTART_RSS}?q=by:{username}&type=deviation"
        else:
            username = self._normalize_username(source)
            rss_url = f"{DEVIANTART_RSS}?q=by:{username}&type=deviation"

        results: list[ScraperResult] = []
        offset = 0

        while len(results) < limit:
            paginated_url = f"{rss_url}&offset={offset}&limit=60"
            resp = await self.fetch(paginated_url)
            deviations = self._parse_rss(resp.text, limit - len(results))

            if not deviations:
                break

            for deviation in deviations:
                if len(results) >= limit:
                    break
                results.append(
                    self.make_result(
                        ContentType.IMAGE, deviation, url=deviation.get("url", "")
                    )
                )

            offset += 60

        return results

    async def scrape_deviation(self, deviation_url: str) -> list[ScraperResult]:
        """Scrape detailed data for a single deviation.

        Args:
            deviation_url: Full URL to the deviation page.
        """
        resp = await self.fetch(deviation_url)
        soup = BeautifulSoup(resp.text, "lxml")

        deviation = self._extract_deviation_detail(soup, deviation_url)

        return [self.make_result(ContentType.IMAGE, deviation, url=deviation_url)]

    async def scrape_gallery(
        self, username: str, folder: str = "all", max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape a specific gallery folder.

        Args:
            username: Artist username.
            folder: Gallery folder name or 'all'.
            max_results: Maximum deviations.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(username)

        if folder == "all":
            rss_url = f"{DEVIANTART_RSS}?q=by:{username}&type=deviation"
        else:
            rss_url = (
                f"{DEVIANTART_RSS}?q=by:{username}+in:gallery/{quote_plus(folder)}"
                f"&type=deviation"
            )

        results: list[ScraperResult] = []
        offset = 0

        while len(results) < limit:
            paginated_url = f"{rss_url}&offset={offset}&limit=60"
            resp = await self.fetch(paginated_url)
            deviations = self._parse_rss(resp.text, limit - len(results))

            if not deviations:
                break

            for deviation in deviations:
                if len(results) >= limit:
                    break
                results.append(
                    self.make_result(
                        ContentType.IMAGE, deviation, url=deviation.get("url", "")
                    )
                )

            offset += 60

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search DeviantArt for deviations via the RSS feed.

        Args:
            query: Search query string.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        rss_url = f"{DEVIANTART_RSS}?q={quote_plus(query)}&type=deviation"

        results: list[ScraperResult] = []
        offset = 0

        while len(results) < limit:
            paginated_url = f"{rss_url}&offset={offset}&limit=60"
            resp = await self.fetch(paginated_url)
            deviations = self._parse_rss(resp.text, limit - len(results))

            if not deviations:
                break

            for deviation in deviations:
                if len(results) >= limit:
                    break
                results.append(
                    self.make_result(
                        ContentType.SEARCH, deviation, url=deviation.get("url", "")
                    )
                )

            offset += 60

        return results

    async def search_artists(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search for artists on DeviantArt.

        Args:
            query: Search query for artists.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        search_url = f"{DEVIANTART_BASE}/search/artists?q={quote_plus(query)}"

        resp = await self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        results: list[ScraperResult] = []

        # Find artist cards/links in search results
        for link in soup.find_all("a", href=re.compile(r"deviantart\.com/[a-zA-Z0-9_-]+$")):
            if len(results) >= limit:
                break

            href = link["href"]
            username = href.rstrip("/").split("/")[-1]

            # Skip common non-profile links
            if username.lower() in (
                "about", "team", "join", "search", "tag", "popular", "newest",
                "daily-deviations", "groups", "forum", "chat", "shop",
            ):
                continue

            name_el = link.find(["span", "strong", "h3"])
            name = name_el.get_text(strip=True) if name_el else username

            img = link.find("img")
            avatar = img.get("src", "") if img else ""

            artist = {
                "username": username,
                "name": name,
                "avatar": avatar,
                "url": f"{DEVIANTART_BASE}/{username}",
            }
            results.append(
                self.make_result(ContentType.PROFILE, artist, url=artist["url"])
            )

        return results

    # --- RSS parsing ---

    def _parse_rss(self, xml_text: str, limit: int) -> list[dict]:
        """Parse DeviantArt RSS feed into deviation dicts."""
        deviations: list[dict] = []

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Failed to parse DeviantArt RSS feed")
            return deviations

        channel = root.find("channel")
        if channel is None:
            return deviations

        for item in channel.findall("item"):
            if len(deviations) >= limit:
                break

            title = self._xml_text(item, "title")
            link = self._xml_text(item, "link")
            pub_date = self._xml_text(item, "pubDate")
            description = self._xml_text(item, "description")

            # Extract author from media:credit or dc:creator
            author = ""
            credit = item.find("media:credit", _NS)
            if credit is not None and credit.text:
                author = credit.text.strip()
            if not author:
                creator = item.find(
                    "{http://purl.org/dc/elements/1.1/}creator"
                )
                if creator is not None and creator.text:
                    author = creator.text.strip()

            # Extract media content (the image/video URL)
            media_url = ""
            media_content = item.find("media:content", _NS)
            if media_content is not None:
                media_url = media_content.get("url", "")

            # Extract thumbnail
            thumbnail = ""
            media_thumb = item.find("media:thumbnail", _NS)
            if media_thumb is not None:
                thumbnail = media_thumb.get("url", "")

            # Extract rating
            rating = ""
            media_rating = item.find("media:rating", _NS)
            if media_rating is not None and media_rating.text:
                rating = media_rating.text.strip()

            # Extract categories/tags
            categories = [c.text for c in item.findall("media:category", _NS) if c.text]
            if not categories:
                categories = [c.text for c in item.findall("category") if c.text]

            # Extract keywords
            keywords_el = item.find("media:keywords", _NS)
            keywords = []
            if keywords_el is not None and keywords_el.text:
                keywords = [
                    k.strip() for k in keywords_el.text.split(",") if k.strip()
                ]

            # Clean description HTML
            clean_desc = ""
            if description:
                desc_soup = BeautifulSoup(description, "lxml")
                clean_desc = desc_soup.get_text(strip=True)[:500]

            # Extract copyright/license
            copyright_text = ""
            cc = item.find("media:copyright", _NS)
            if cc is not None and cc.text:
                copyright_text = cc.text.strip()

            deviation = {
                "title": title,
                "url": link,
                "author": author,
                "published_date": pub_date,
                "description": clean_desc,
                "media_url": media_url,
                "thumbnail": thumbnail,
                "rating": rating,
                "categories": categories,
                "keywords": keywords,
                "copyright": copyright_text,
            }
            deviations.append(deviation)

        return deviations

    # --- Web scraping helpers ---

    def _extract_profile(self, soup: BeautifulSoup, username: str) -> dict:
        """Extract artist profile data from the profile page."""
        name = self._meta(soup, "og:title") or username
        # Remove " | DeviantArt" suffix
        name = re.sub(r"\s*[|]\s*DeviantArt.*$", "", name).strip()

        bio = self._meta(soup, "og:description") or ""
        avatar = self._meta(soup, "og:image") or ""

        # Try to extract stats from the page
        stats = self._extract_stats(soup)

        # Extract user tagline or headline
        tagline = ""
        tagline_el = soup.find(class_=re.compile(r"tagline|headline|user-info"))
        if tagline_el:
            tagline = tagline_el.get_text(strip=True)

        # Extract join date
        join_date = ""
        for el in soup.find_all(string=re.compile(r"member since|joined", re.I)):
            text = str(el).strip()
            date_match = re.search(
                r"(?:member since|joined)\s*(.+)", text, re.I
            )
            if date_match:
                join_date = date_match.group(1).strip()
                break

        # Extract country/location
        country = ""
        location_el = soup.find(class_=re.compile(r"country|location"))
        if location_el:
            country = location_el.get_text(strip=True)

        # Extract groups
        groups: list[str] = []
        for group_link in soup.find_all(
            "a", href=re.compile(r"deviantart\.com/[a-z0-9_-]+$"), limit=20
        ):
            group_name = group_link.get_text(strip=True)
            if group_name and group_name.lower() != username.lower():
                groups.append(group_name)

        return {
            "username": username,
            "name": name,
            "bio": bio,
            "tagline": tagline,
            "avatar": avatar,
            "country": country,
            "join_date": join_date,
            "deviations_count": stats.get("deviations", 0),
            "watchers_count": stats.get("watchers", 0),
            "watching_count": stats.get("watching", 0),
            "favourites_count": stats.get("favourites", 0),
            "comments_count": stats.get("comments", 0),
            "pageviews_count": stats.get("pageviews", 0),
        }

    def _extract_deviation_detail(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract detailed deviation data from a deviation page."""
        title = self._meta(soup, "og:title") or ""
        title = re.sub(r"\s*on DeviantArt.*$", "", title, flags=re.I).strip()

        description = self._meta(soup, "og:description") or ""
        image = self._meta(soup, "og:image") or ""

        # Extract full description / artist comments
        desc_el = soup.find(class_=re.compile(r"deviation.*desc|text-content|artist-comment"))
        full_description = ""
        if desc_el:
            full_description = desc_el.get_text(separator="\n", strip=True)[:5000]

        # Extract tags
        tags: list[str] = []
        for tag_link in soup.find_all("a", href=re.compile(r"/tag/")):
            tag_text = tag_link.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        # Extract author
        author = ""
        author_link = soup.find("a", class_=re.compile(r"user|author"))
        if author_link:
            author = author_link.get_text(strip=True)
        if not author:
            author = self._meta(soup, "author") or ""

        # Extract published date
        time_el = soup.find("time")
        published = ""
        if time_el:
            published = time_el.get("datetime", "") or time_el.get_text(strip=True)

        # Extract stats
        stats = self._extract_stats(soup)

        # Extract image dimensions from meta or data attributes
        width = 0
        height = 0
        og_width = self._meta(soup, "og:image:width")
        og_height = self._meta(soup, "og:image:height")
        if og_width:
            try:
                width = int(og_width)
            except ValueError:
                pass
        if og_height:
            try:
                height = int(og_height)
            except ValueError:
                pass

        return {
            "title": title,
            "description": description,
            "full_description": full_description,
            "url": url,
            "image": image,
            "width": width,
            "height": height,
            "author": author,
            "published_date": published,
            "tags": tags,
            "favourites_count": stats.get("favourites", 0),
            "comments_count": stats.get("comments", 0),
            "views_count": stats.get("views", 0),
            "downloads_count": stats.get("downloads", 0),
        }

    def _extract_stats(self, soup: BeautifulSoup) -> dict[str, int]:
        """Extract numeric stats from stat elements on the page."""
        stats: dict[str, int] = {}

        for el in soup.find_all(class_=re.compile(r"stat|count|metric"), limit=30):
            text = el.get_text(strip=True).lower()
            value = self._parse_numeric(text)
            if value <= 0:
                continue

            if "deviation" in text:
                stats["deviations"] = value
            elif "watcher" in text and "watching" not in text:
                stats["watchers"] = value
            elif "watching" in text:
                stats["watching"] = value
            elif "fav" in text:
                stats["favourites"] = value
            elif "comment" in text:
                stats["comments"] = value
            elif "view" in text or "pageview" in text:
                stats.setdefault("views", value)
                if "pageview" in text:
                    stats["pageviews"] = value
            elif "download" in text:
                stats["downloads"] = value

        return stats

    # --- Utility helpers ---

    def _normalize_username(self, identifier: str) -> str:
        """Normalize an identifier to a DeviantArt username."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            parts = path.split("/")
            return parts[0] if parts else identifier
        return identifier.strip("/").strip("@")

    @staticmethod
    def _xml_text(element: Any, tag: str) -> str:
        """Get text content of an XML sub-element."""
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _parse_numeric(text: str) -> int:
        """Parse a human-readable number (e.g. '1.2K', '500')."""
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
