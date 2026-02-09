"""Product Hunt scraper using web scraping.

No API key required. Scrapes public product pages, daily/weekly listings,
and search results from the Product Hunt website. The official GraphQL API
requires authentication, so this scraper parses structured data embedded
in the HTML pages instead.
Supports: product profiles, daily/weekly top products, search.
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

PRODUCTHUNT_BASE = "https://www.producthunt.com"


class ProductHuntScraper(BaseScraper):
    """Product Hunt scraper using web scraping and embedded JSON data.

    No authentication needed. Parses Next.js / Apollo state data embedded
    in Product Hunt pages to extract structured product information.

    Usage:
        scraper = ProductHuntScraper()
        results = await scraper.scrape_profile("notion")
        results = await scraper.scrape_posts("daily", max_results=20)
        results = await scraper.search("ai writing tool", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "producthunt"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Product Hunt product profile page.

        Args:
            identifier: Product slug (e.g. 'notion'), full product URL,
                        or a user profile URL.
        """
        slug = self._normalize_slug(identifier)
        url = f"{PRODUCTHUNT_BASE}/products/{slug}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try to extract structured data from the page
        product = self._extract_product_from_page(soup, slug)
        product["url"] = url

        return [self.make_result(ContentType.PROFILE, product, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape products from daily, weekly, or monthly listings.

        Args:
            source: One of 'daily', 'weekly', 'monthly', a dated URL
                    (e.g. 'posts/2025-01-15'), or 'topics/<topic-slug>'.
            max_results: Maximum products to return.
        """
        limit = max_results or self.config.max_results

        if source.lower() == "daily":
            url = PRODUCTHUNT_BASE
        elif source.lower() == "weekly":
            url = f"{PRODUCTHUNT_BASE}/newsletter/weekly"
        elif source.lower() == "monthly":
            url = f"{PRODUCTHUNT_BASE}/newsletter/monthly"
        elif source.startswith("http"):
            url = source
        elif source.startswith("topics/"):
            url = f"{PRODUCTHUNT_BASE}/{source}"
        elif source.startswith("posts/"):
            url = f"{PRODUCTHUNT_BASE}/time-travel/{source.replace('posts/', '')}"
        else:
            url = f"{PRODUCTHUNT_BASE}/topics/{source}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        products = self._extract_product_list(soup, limit)

        results: list[ScraperResult] = []
        for product in products[:limit]:
            results.append(
                self.make_result(ContentType.POST, product, url=product.get("url", ""))
            )

        return results

    async def scrape_leaderboard(
        self, period: str = "daily", max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape the Product Hunt leaderboard.

        Args:
            period: One of 'daily', 'weekly', 'monthly'.
            max_results: Maximum products to return.
        """
        limit = max_results or self.config.max_results
        url = f"{PRODUCTHUNT_BASE}/leaderboard/{period}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        products = self._extract_product_list(soup, limit)

        results: list[ScraperResult] = []
        for rank, product in enumerate(products[:limit], start=1):
            product["rank"] = rank
            results.append(
                self.make_result(
                    ContentType.TRENDING, product, url=product.get("url", "")
                )
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Product Hunt for products.

        Args:
            query: Search query string.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results
        search_url = f"{PRODUCTHUNT_BASE}/search?q={quote_plus(query)}"

        resp = await self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try to extract products from the search results page
        products = self._extract_product_list(soup, limit)

        # Fallback: parse search result links
        if not products:
            products = self._extract_search_links(soup, limit)

        results: list[ScraperResult] = []
        for product in products[:limit]:
            results.append(
                self.make_result(
                    ContentType.SEARCH, product, url=product.get("url", "")
                )
            )

        return results

    # --- Extraction helpers ---

    def _extract_product_from_page(self, soup: BeautifulSoup, slug: str) -> dict:
        """Extract product profile data from a product page."""
        # Try to find Next.js / Apollo embedded JSON data
        for script in soup.find_all("script", {"type": "application/json"}):
            if script.string:
                try:
                    data = json.loads(script.string)
                    product = self._find_product_in_data(data, slug)
                    if product:
                        return product
                except json.JSONDecodeError:
                    continue

        # Try __NEXT_DATA__
        next_data = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                product = self._find_product_in_data(data, slug)
                if product:
                    return product
            except json.JSONDecodeError:
                pass

        # Try JSON-LD structured data
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            if script.string:
                try:
                    ld = json.loads(script.string)
                    if isinstance(ld, dict) and ld.get("name"):
                        return {
                            "name": ld.get("name", slug),
                            "tagline": ld.get("description", ""),
                            "url": ld.get("url", ""),
                            "image": ld.get("image", ""),
                        }
                except json.JSONDecodeError:
                    pass

        # Fallback to meta tags
        return {
            "slug": slug,
            "name": self._meta(soup, "og:title") or slug,
            "tagline": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
            "twitter": self._meta(soup, "twitter:site") or "",
        }

    def _find_product_in_data(self, data: Any, slug: str) -> dict | None:
        """Recursively search embedded JSON for product data."""
        if isinstance(data, dict):
            # Check if this dict looks like a product node
            if (
                data.get("slug") == slug
                or data.get("type") == "Post"
                or (data.get("name") and data.get("tagline"))
            ):
                return {
                    "product_id": data.get("id", ""),
                    "slug": data.get("slug", slug),
                    "name": data.get("name", ""),
                    "tagline": data.get("tagline", ""),
                    "description": data.get("description", ""),
                    "url": data.get("url", "")
                    or data.get("websiteUrl", "")
                    or f"{PRODUCTHUNT_BASE}/products/{slug}",
                    "website": data.get("websiteUrl", "") or data.get("website", ""),
                    "votes_count": data.get("votesCount", 0),
                    "comments_count": data.get("commentsCount", 0),
                    "reviews_rating": data.get("reviewsRating", 0),
                    "reviews_count": data.get("reviewsCount", 0),
                    "followers_count": data.get("followersCount", 0),
                    "image": (
                        data.get("thumbnail", {}).get("url", "")
                        if isinstance(data.get("thumbnail"), dict)
                        else data.get("thumbnailUrl", "")
                    ),
                    "topics": [
                        t.get("name", "")
                        for t in data.get("topics", {}).get("edges", [])
                        if isinstance(t, dict) and t.get("name")
                    ]
                    if isinstance(data.get("topics"), dict)
                    else [],
                    "makers": [
                        m.get("name", "")
                        for m in data.get("makers", [])
                        if isinstance(m, dict)
                    ],
                    "launched_at": data.get("createdAt", "") or data.get("featuredAt", ""),
                }
            for v in data.values():
                result = self._find_product_in_data(v, slug)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_product_in_data(item, slug)
                if result:
                    return result
        return None

    def _extract_product_list(self, soup: BeautifulSoup, limit: int) -> list[dict]:
        """Extract a list of products from a listing page."""
        products: list[dict] = []
        seen: set[str] = set()

        # Try embedded JSON first
        for script in soup.find_all("script", {"type": "application/json"}):
            if script.string and len(products) < limit:
                try:
                    data = json.loads(script.string)
                    self._find_products_in_data(data, products, limit, seen)
                except json.JSONDecodeError:
                    continue

        # Try __NEXT_DATA__
        next_data = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data and next_data.string and len(products) < limit:
            try:
                data = json.loads(next_data.string)
                self._find_products_in_data(data, products, limit, seen)
            except json.JSONDecodeError:
                pass

        # Fallback: parse product card links from HTML
        if not products:
            for link in soup.find_all("a", href=re.compile(r"/posts/[a-z0-9-]+")):
                href = link["href"]
                slug = href.split("/posts/")[-1].strip("/").split("?")[0]
                if not slug or slug in seen:
                    continue
                seen.add(slug)

                # Try to find name and tagline near the link
                parent = link.find_parent(["div", "li", "article"])
                name = ""
                tagline = ""
                if parent:
                    heading = parent.find(["h2", "h3", "strong"])
                    name = heading.get_text(strip=True) if heading else ""
                    p_tag = parent.find("p")
                    tagline = p_tag.get_text(strip=True) if p_tag else ""

                products.append({
                    "slug": slug,
                    "name": name or slug,
                    "tagline": tagline,
                    "url": f"{PRODUCTHUNT_BASE}/posts/{slug}",
                })
                if len(products) >= limit:
                    break

        return products

    def _find_products_in_data(
        self, data: Any, products: list[dict], limit: int, seen: set[str]
    ):
        """Recursively find product entries in embedded JSON."""
        if len(products) >= limit:
            return
        if isinstance(data, dict):
            slug = data.get("slug", "")
            # Looks like a product/post entry
            if slug and data.get("name") and data.get("tagline") and slug not in seen:
                seen.add(slug)
                products.append({
                    "product_id": data.get("id", ""),
                    "slug": slug,
                    "name": data.get("name", ""),
                    "tagline": data.get("tagline", ""),
                    "url": f"{PRODUCTHUNT_BASE}/posts/{slug}",
                    "votes_count": data.get("votesCount", 0),
                    "comments_count": data.get("commentsCount", 0),
                    "image": (
                        data.get("thumbnail", {}).get("url", "")
                        if isinstance(data.get("thumbnail"), dict)
                        else data.get("thumbnailUrl", "")
                    ),
                    "topics": [
                        t.get("name", "")
                        for t in data.get("topics", {}).get("edges", [])
                        if isinstance(t, dict) and t.get("name")
                    ]
                    if isinstance(data.get("topics"), dict)
                    else [],
                    "launched_at": data.get("createdAt", "") or data.get("featuredAt", ""),
                })
            for v in data.values():
                self._find_products_in_data(v, products, limit, seen)
        elif isinstance(data, list):
            for item in data:
                self._find_products_in_data(item, products, limit, seen)

    def _extract_search_links(self, soup: BeautifulSoup, limit: int) -> list[dict]:
        """Fallback search extraction from anchor tags."""
        results: list[dict] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/posts/" not in href and "/products/" not in href:
                continue

            slug = href.split("/")[-1].strip("/").split("?")[0]
            if not slug or slug in seen:
                continue
            seen.add(slug)

            name_el = link.find(["h3", "h2", "strong", "span"])
            name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)

            if not name or len(name) < 2:
                continue

            full_url = href if href.startswith("http") else f"{PRODUCTHUNT_BASE}{href}"
            results.append({
                "slug": slug,
                "name": name,
                "url": full_url,
            })
            if len(results) >= limit:
                break

        return results

    # --- Utility helpers ---

    def _normalize_slug(self, identifier: str) -> str:
        """Normalize an identifier to a product slug."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            # Handle /products/slug or /posts/slug
            parts = path.split("/")
            return parts[-1] if parts else identifier
        return identifier.strip("/").lower()

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return tag.get("content", "") if tag else ""
