"""Substack scraper using RSS feeds and HTML parsing.

No API key required. Every Substack publication exposes an RSS feed at /feed,
which provides article metadata. Full article content is scraped from the HTML
pages. Tag-based discovery uses Substack's reader endpoints.

Supports: newsletter profiles, posts/articles, search by tag.
"""

import logging
import re
from typing import Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

SUBSTACK_READER = "https://substack.com"


class SubstackScraper(BaseScraper):
    """Substack scraper using RSS feeds and HTML parsing.

    Every Substack blog exposes /feed for RSS. Profile and article data
    are scraped from the rendered HTML pages. Search leverages Substack's
    public reader/search endpoints.

    Usage:
        scraper = SubstackScraper()
        results = await scraper.scrape_profile("platformer")
        results = await scraper.scrape_posts("platformer", max_results=20)
        results = await scraper.search("artificial intelligence", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "substack"

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Substack newsletter profile.

        Args:
            identifier: Subdomain name (e.g. "platformer"), custom domain,
                        or full URL.
        """
        base_url = self._resolve_base_url(identifier)
        resp = await self.fetch(base_url)
        soup = BeautifulSoup(resp.text, "lxml")

        profile = {
            "name": self._meta(soup, "og:title") or self._meta(soup, "title") or identifier,
            "description": (
                self._meta(soup, "og:description")
                or self._meta(soup, "description")
                or ""
            ),
            "url": base_url,
            "image": self._meta(soup, "og:image") or "",
            "author": self._extract_author(soup),
            "twitter": self._meta(soup, "twitter:site") or "",
            "type": self._meta(soup, "og:type") or "website",
        }

        # Try to extract subscriber count from page content
        subscriber_el = soup.find(string=re.compile(r"subscriber", re.IGNORECASE))
        if subscriber_el:
            match = re.search(r"([\d,]+)\s*subscriber", str(subscriber_el), re.IGNORECASE)
            if match:
                profile["subscriber_count"] = int(match.group(1).replace(",", ""))

        return [self.make_result(ContentType.PROFILE, profile, url=base_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape articles from a Substack newsletter via its RSS feed.

        Args:
            source: Subdomain name, custom domain, or full URL.
            max_results: Maximum number of articles to return.
        """
        limit = max_results or self.config.max_results
        base_url = self._resolve_base_url(source)
        feed_url = f"{base_url}/feed"

        resp = await self.fetch(feed_url)
        results = self._parse_rss(resp.text, limit)

        return results

    async def scrape_article(self, article_url: str) -> list[ScraperResult]:
        """Scrape full content of a single Substack article.

        Args:
            article_url: Full URL to the article page.
        """
        resp = await self.fetch(article_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Substack articles use a predictable structure
        body_el = (
            soup.find("div", class_=re.compile(r"body|post-content|available-content"))
            or soup.find("article")
            or soup.find("div", {"role": "main"})
        )

        content = ""
        if body_el:
            paragraphs = body_el.find_all(
                ["p", "h1", "h2", "h3", "h4", "blockquote", "pre", "li"]
            )
            content = "\n\n".join(
                p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
            )

        # Extract images from the article body
        images: list[str] = []
        if body_el:
            for img in body_el.find_all("img", src=True):
                src = img["src"]
                if "avatar" not in src and "logo" not in src and src not in images:
                    images.append(src)

        article = {
            "title": self._meta(soup, "og:title") or "",
            "subtitle": self._meta(soup, "og:description") or "",
            "author": self._extract_author(soup),
            "published_time": (
                self._meta(soup, "article:published_time")
                or self._extract_publish_date(soup)
            ),
            "content": content,
            "url": article_url,
            "image": self._meta(soup, "og:image") or "",
            "images": images,
            "likes": self._extract_like_count(soup),
            "comments": self._extract_comment_count(soup),
        }

        return [self.make_result(ContentType.ARTICLE, article, url=article_url)]

    async def scrape_tag(
        self, tag: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape newsletters/posts related to a Substack tag/topic.

        Args:
            tag: Topic tag (e.g. "technology", "politics").
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        # Substack reader exposes topic pages
        tag_slug = tag.lower().strip().replace(" ", "-")
        url = f"{SUBSTACK_READER}/topics/{tag_slug}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        results: list[ScraperResult] = []

        # Find publication/article links in the topic page
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href or "javascript:" in href:
                continue
            # Look for links to individual newsletters or posts
            if ".substack.com" in href or "/p/" in href:
                title_el = link.find(["h2", "h3", "h4", "span"])
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue
                # Deduplicate by URL
                full_url = href if href.startswith("http") else f"{SUBSTACK_READER}{href}"
                if any(r.url == full_url for r in results):
                    continue
                entry = {
                    "title": title,
                    "url": full_url,
                    "tag": tag,
                }
                results.append(
                    self.make_result(ContentType.ARTICLE, entry, url=full_url)
                )
                if len(results) >= limit:
                    break

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Substack for newsletters and articles.

        Uses the public Substack search/reader page.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Substack exposes a search endpoint on the reader
        search_url = f"{SUBSTACK_READER}/search/{quote(query)}"
        resp = await self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        results: list[ScraperResult] = []

        # Parse search result cards
        for card in soup.find_all(
            ["div", "article", "a"], class_=re.compile(r"post|result|card|item", re.IGNORECASE)
        ):
            link = card if card.name == "a" else card.find("a", href=True)
            if not link or not link.get("href"):
                continue
            href = link["href"]
            if not (".substack.com" in href or "/p/" in href):
                continue

            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            preview_el = card.find("p")
            preview = preview_el.get_text(strip=True)[:300] if preview_el else ""

            full_url = href if href.startswith("http") else f"{SUBSTACK_READER}{href}"
            if any(r.url == full_url for r in results):
                continue

            entry = {
                "title": title,
                "preview": preview,
                "url": full_url,
            }
            results.append(
                self.make_result(ContentType.SEARCH, entry, url=full_url)
            )
            if len(results) >= limit:
                break

        # Fallback: try tag-based discovery when search page yields nothing
        if not results:
            tag_slug = query.lower().replace(" ", "-")
            try:
                return await self.scrape_tag(tag_slug, max_results=limit)
            except Exception:
                logger.debug("Tag fallback failed for query: %s", query)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_base_url(self, identifier: str) -> str:
        """Turn a subdomain name, custom domain, or URL into the base URL."""
        if identifier.startswith("http"):
            parsed = urlparse(identifier)
            return f"{parsed.scheme}://{parsed.netloc}"
        # Bare name -> standard Substack subdomain
        slug = identifier.strip().strip("/").lower()
        return f"https://{slug}.substack.com"

    def _parse_rss(self, xml_text: str, limit: int) -> list[ScraperResult]:
        """Parse an RSS/Atom feed and return ScraperResult articles."""
        results: list[ScraperResult] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Failed to parse Substack RSS feed")
            return results

        # Standard RSS
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                if len(results) >= limit:
                    break
                results.append(self._rss_item_to_result(item))
            return results

        # Atom fallback (namespace)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            if len(results) >= limit:
                break
            title = self._xml_text_ns(entry, "atom:title", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = self._xml_text_ns(entry, "atom:summary", ns)
            published = (
                self._xml_text_ns(entry, "atom:published", ns)
                or self._xml_text_ns(entry, "atom:updated", ns)
            )
            author_el = entry.find("atom:author", ns)
            author = ""
            if author_el is not None:
                name_el = author_el.find("atom:name", ns)
                author = name_el.text.strip() if name_el is not None and name_el.text else ""

            if summary:
                summary_soup = BeautifulSoup(summary, "lxml")
                summary = summary_soup.get_text(strip=True)[:500]

            article = {
                "title": title,
                "url": link,
                "author": author,
                "description": summary,
                "published_date": published,
            }
            results.append(
                self.make_result(ContentType.ARTICLE, article, url=link)
            )

        return results

    def _rss_item_to_result(self, item: ElementTree.Element) -> ScraperResult:
        """Convert a single RSS <item> to a ScraperResult."""
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

        # dc:creator for author
        creator = item.find("{http://purl.org/dc/elements/1.1/}creator")
        author = creator.text.strip() if creator is not None and creator.text else ""

        # Enclosure for podcast/audio posts
        enclosure = item.find("enclosure")
        audio_url = ""
        if enclosure is not None:
            enc_type = enclosure.get("type", "")
            if "audio" in enc_type:
                audio_url = enclosure.get("url", "")

        categories = [c.text for c in item.findall("category") if c.text]

        article: dict[str, Any] = {
            "title": title,
            "url": link,
            "author": author,
            "description": clean_desc,
            "published_date": pub_date,
            "tags": categories,
        }
        if audio_url:
            article["audio_url"] = audio_url

        return self.make_result(ContentType.ARTICLE, article, url=link)

    # ------------------------------------------------------------------
    # Extraction utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _xml_text(element: ElementTree.Element, tag: str) -> str:
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _xml_text_ns(element: ElementTree.Element, tag: str, ns: dict) -> str:
        el = element.find(tag, ns)
        return el.text.strip() if el is not None and el.text else ""

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
    def _extract_author(soup: BeautifulSoup) -> str:
        """Extract the author/publication owner from the page."""
        # Try meta author tag
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author:
            return meta_author.get("content", "")
        # Try link with rel=author
        author_link = soup.find("a", rel="author")
        if author_link:
            return author_link.get_text(strip=True)
        # Try twitter:creator
        tc = soup.find("meta", attrs={"name": "twitter:creator"})
        if tc:
            return tc.get("content", "")
        return ""

    @staticmethod
    def _extract_publish_date(soup: BeautifulSoup) -> str:
        """Attempt to pull publish date from time element or JSON-LD."""
        time_el = soup.find("time")
        if time_el:
            return time_el.get("datetime", time_el.get_text(strip=True))
        return ""

    @staticmethod
    def _extract_like_count(soup: BeautifulSoup) -> int:
        """Extract like/heart count from the article page."""
        for el in soup.find_all(class_=re.compile(r"like|heart", re.IGNORECASE)):
            text = el.get_text(strip=True)
            match = re.search(r"(\d[\d,]*)", text)
            if match:
                return int(match.group(1).replace(",", ""))
        return 0

    @staticmethod
    def _extract_comment_count(soup: BeautifulSoup) -> int:
        """Extract comment count from the article page."""
        for el in soup.find_all(string=re.compile(r"\d+\s*comment", re.IGNORECASE)):
            match = re.search(r"(\d+)\s*comment", str(el), re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 0
