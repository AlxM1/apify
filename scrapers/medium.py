"""Medium scraper using web scraping and RSS feeds.

No API key required. Uses RSS feeds for article discovery and HTML parsing for full content.
Supports: articles, profiles, publications, tags, search.
"""

import logging
import re
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

MEDIUM_BASE = "https://medium.com"


class MediumScraper(BaseScraper):
    """Medium scraper using RSS feeds and HTML parsing.

    No authentication needed. Uses Medium's RSS endpoint for discovery
    and page scraping for full article content.

    Usage:
        scraper = MediumScraper()
        results = await scraper.scrape_profile("@elonmusk")
        results = await scraper.scrape_posts("@elonmusk", max_results=10)
        results = await scraper.search("machine learning", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "medium"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Medium user/publication profile.

        Args:
            identifier: Username (@handle) or publication URL.
        """
        handle = self._normalize_handle(identifier)

        # Fetch the profile page
        url = f"{MEDIUM_BASE}/{handle}"
        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract profile data from meta tags and page content
        profile = {
            "handle": handle,
            "name": self._meta(soup, "og:title") or self._meta(soup, "title") or handle,
            "description": self._meta(soup, "og:description") or self._meta(soup, "description") or "",
            "image": self._meta(soup, "og:image") or "",
            "url": url,
            "twitter": self._meta(soup, "twitter:creator") or "",
        }

        return [self.make_result(ContentType.PROFILE, profile, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape articles from a Medium user or publication via RSS.

        Args:
            source: Username (@handle), publication name, or tag.
            max_results: Maximum articles to fetch.
        """
        limit = max_results or self.config.max_results
        rss_url = self._build_rss_url(source)

        resp = await self.fetch(rss_url)
        results = self._parse_rss(resp.text, limit)

        return results

    async def scrape_article(self, article_url: str) -> list[ScraperResult]:
        """Scrape full content of a single Medium article.

        Args:
            article_url: Full URL to the Medium article.
        """
        resp = await self.fetch(article_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract article content
        article_tag = soup.find("article")
        if not article_tag:
            article_tag = soup.find("div", {"role": "main"})

        content = ""
        if article_tag:
            # Get text content, preserving paragraph structure
            paragraphs = article_tag.find_all(["p", "h1", "h2", "h3", "h4", "blockquote", "pre", "li"])
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

        article = {
            "title": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "author": self._meta(soup, "author") or "",
            "published_time": self._meta(soup, "article:published_time") or "",
            "content": content,
            "url": article_url,
            "image": self._meta(soup, "og:image") or "",
            "reading_time": self._extract_reading_time(soup),
            "claps": self._extract_claps(soup),
            "tags": self._extract_tags(soup),
        }

        return [self.make_result(ContentType.ARTICLE, article, url=article_url)]

    async def scrape_tag(
        self, tag: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape articles by tag via RSS.

        Args:
            tag: Medium tag (e.g. "machine-learning").
        """
        return await self.scrape_posts(f"tag/{tag}", max_results)

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Medium articles.

        Uses Medium's tag/search system and Google site search as fallback.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Medium doesn't have a public search API, so we use the tag RSS
        # for single-word queries and scrape search results page for others
        tag = query.lower().replace(" ", "-")
        rss_url = f"{MEDIUM_BASE}/feed/tag/{tag}"

        try:
            resp = await self.fetch(rss_url)
            results = self._parse_rss(resp.text, limit)
            if results:
                return results
        except Exception:
            pass

        # Fallback: scrape the search results page
        search_url = f"{MEDIUM_BASE}/search?q={query}"
        resp = await self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        results = []
        # Find article links in search results
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/@" in href or "/p/" in href:
                # Looks like an article link
                title_el = link.find(["h2", "h3"])
                if title_el:
                    article = {
                        "title": title_el.get_text(strip=True),
                        "url": href if href.startswith("http") else f"{MEDIUM_BASE}{href}",
                    }
                    results.append(
                        self.make_result(ContentType.SEARCH, article, url=article["url"])
                    )
                    if len(results) >= limit:
                        break

        return results

    def _normalize_handle(self, identifier: str) -> str:
        if identifier.startswith("http"):
            from urllib.parse import urlparse
            path = urlparse(identifier).path.strip("/")
            return path.split("/")[0] if path else identifier
        if not identifier.startswith("@"):
            return f"@{identifier}"
        return identifier

    def _build_rss_url(self, source: str) -> str:
        if source.startswith("http"):
            return f"{source}/feed" if "/feed" not in source else source
        if source.startswith("tag/"):
            return f"{MEDIUM_BASE}/feed/{source}"
        handle = self._normalize_handle(source)
        return f"{MEDIUM_BASE}/feed/{handle}"

    def _parse_rss(self, xml_text: str, limit: int) -> list[ScraperResult]:
        results = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Failed to parse RSS feed")
            return results

        channel = root.find("channel")
        if channel is None:
            return results

        for item in channel.findall("item"):
            if len(results) >= limit:
                break

            title = self._xml_text(item, "title")
            link = self._xml_text(item, "link")
            description = self._xml_text(item, "description")
            pub_date = self._xml_text(item, "pubDate")

            # Clean HTML from description
            if description:
                desc_soup = BeautifulSoup(description, "lxml")
                clean_desc = desc_soup.get_text(strip=True)[:500]
            else:
                clean_desc = ""

            # Extract author from dc:creator
            creator = item.find("{http://purl.org/dc/elements/1.1/}creator")
            author = creator.text if creator is not None and creator.text else ""

            # Extract categories/tags
            categories = [c.text for c in item.findall("category") if c.text]

            article = {
                "title": title,
                "url": link,
                "author": author,
                "description": clean_desc,
                "published_date": pub_date,
                "tags": categories,
            }
            results.append(
                self.make_result(ContentType.ARTICLE, article, url=link)
            )

        return results

    @staticmethod
    def _xml_text(element, tag: str) -> str:
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag:
            return tag.get("content", "")
        return ""

    @staticmethod
    def _extract_reading_time(soup: BeautifulSoup) -> str:
        # Medium shows reading time in various ways
        for el in soup.find_all(string=re.compile(r"\d+\s*min\s*read")):
            match = re.search(r"(\d+)\s*min\s*read", str(el))
            if match:
                return f"{match.group(1)} min"
        return ""

    @staticmethod
    def _extract_claps(soup: BeautifulSoup) -> int:
        # Try to find clap count
        for button in soup.find_all("button"):
            text = button.get_text(strip=True)
            if text and text.replace(",", "").replace(".", "").replace("K", "").replace("M", "").isdigit():
                text = text.replace(",", "")
                if "K" in text:
                    return int(float(text.replace("K", "")) * 1000)
                if "M" in text:
                    return int(float(text.replace("M", "")) * 1000000)
                try:
                    return int(text)
                except ValueError:
                    pass
        return 0

    @staticmethod
    def _extract_tags(soup: BeautifulSoup) -> list[str]:
        tags = []
        for link in soup.find_all("a", href=True):
            if "/tag/" in link["href"]:
                tag_text = link.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        return tags
