"""Tumblr scraper using web scraping and RSS feeds.

No API key required. Uses Tumblr's public blog endpoints and RSS feeds.
Supports: blog profiles, posts, tags, search.
"""

import logging
import re
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

TUMBLR_API_V2 = "https://api.tumblr.com/v2"
TUMBLR_BASE = "https://www.tumblr.com"


class TumblrScraper(BaseScraper):
    """Tumblr scraper using public endpoints and RSS.

    Uses Tumblr's public blog JSON endpoints (no API key needed for basic access)
    and RSS feeds for blog post discovery.

    Usage:
        scraper = TumblrScraper()
        results = await scraper.scrape_profile("staff")
        results = await scraper.scrape_posts("staff", max_results=20)
        results = await scraper.search("digital art", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "tumblr"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Tumblr blog profile.

        Args:
            identifier: Blog name (e.g. "staff") or full URL.
        """
        blog_name = self._normalize_blog(identifier)
        url = f"https://{blog_name}.tumblr.com"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        profile = {
            "blog_name": blog_name,
            "title": self._meta(soup, "og:title") or blog_name,
            "description": self._meta(soup, "og:description") or self._meta(soup, "description") or "",
            "url": url,
            "image": self._meta(soup, "og:image") or "",
            "twitter": self._meta(soup, "twitter:creator") or "",
        }

        return [self.make_result(ContentType.PROFILE, profile, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a Tumblr blog via RSS.

        Args:
            source: Blog name or URL.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        blog_name = self._normalize_blog(source)
        rss_url = f"https://{blog_name}.tumblr.com/rss"

        resp = await self.fetch(rss_url)
        results = self._parse_rss(resp.text, blog_name, limit)

        return results

    async def scrape_post(self, post_url: str) -> list[ScraperResult]:
        """Scrape a single Tumblr post.

        Args:
            post_url: Full URL to the post.
        """
        resp = await self.fetch(post_url)
        soup = BeautifulSoup(resp.text, "lxml")

        post = {
            "title": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "url": post_url,
            "image": self._meta(soup, "og:image") or "",
            "type": self._meta(soup, "og:type") or "post",
            "tags": self._extract_tags(soup),
        }

        # Extract the post content
        article = soup.find("article") or soup.find("div", class_=re.compile(r"post"))
        if article:
            post["content"] = article.get_text(separator="\n", strip=True)[:5000]
            # Extract images from the post
            images = []
            for img in article.find_all("img", src=True):
                src = img["src"]
                if "avatar" not in src and "icon" not in src:
                    images.append(src)
            post["images"] = images

        return [self.make_result(ContentType.POST, post, url=post_url)]

    async def scrape_tag(
        self, tag: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts by tag.

        Args:
            tag: Tumblr tag to search.
        """
        limit = max_results or self.config.max_results
        url = f"{TUMBLR_BASE}/tagged/{tag}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        results = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/post/" in href and href.startswith("http"):
                title = link.get_text(strip=True) or ""
                if title and len(title) > 5:  # Skip short link texts
                    post = {
                        "title": title,
                        "url": href,
                        "tag": tag,
                    }
                    results.append(
                        self.make_result(ContentType.POST, post, url=href)
                    )
                    if len(results) >= limit:
                        break

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Tumblr.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Tumblr search via the web
        search_url = f"{TUMBLR_BASE}/search/{query}"
        resp = await self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        results = []

        # Look for post links in search results
        for article in soup.find_all(["article", "div"], class_=re.compile(r"post|result")):
            link = article.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if "/post/" not in href:
                continue

            title_el = article.find(["h2", "h3", "a"])
            title = title_el.get_text(strip=True) if title_el else ""

            # Get preview text
            text_el = article.find("p")
            preview = text_el.get_text(strip=True)[:300] if text_el else ""

            post = {
                "title": title,
                "preview": preview,
                "url": href if href.startswith("http") else f"{TUMBLR_BASE}{href}",
            }
            results.append(
                self.make_result(ContentType.SEARCH, post, url=post["url"])
            )
            if len(results) >= limit:
                break

        return results

    def _normalize_blog(self, identifier: str) -> str:
        if ".tumblr.com" in identifier:
            return identifier.split(".tumblr.com")[0].replace("https://", "").replace("http://", "")
        if identifier.startswith("http"):
            from urllib.parse import urlparse
            return urlparse(identifier).path.strip("/").split("/")[0]
        return identifier.strip("/").strip("@")

    def _parse_rss(self, xml_text: str, blog_name: str, limit: int) -> list[ScraperResult]:
        results = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning(f"Failed to parse RSS for {blog_name}")
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
                # Extract images
                images = [img["src"] for img in desc_soup.find_all("img", src=True)]
                clean_desc = desc_soup.get_text(strip=True)[:500]
            else:
                images = []
                clean_desc = ""

            categories = [c.text for c in item.findall("category") if c.text]

            post = {
                "blog_name": blog_name,
                "title": title,
                "url": link,
                "description": clean_desc,
                "published_date": pub_date,
                "tags": categories,
                "images": images,
            }
            results.append(
                self.make_result(ContentType.POST, post, url=link)
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
    def _extract_tags(soup: BeautifulSoup) -> list[str]:
        tags = []
        for link in soup.find_all("a", href=True):
            if "/tagged/" in link["href"]:
                tag_text = link.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        return tags
