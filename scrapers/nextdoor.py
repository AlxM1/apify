"""Nextdoor scraper for public business pages and limited public content.

No API key required. Most Nextdoor content is location-gated and requires
authentication, so this scraper focuses on publicly accessible business
pages, public agency pages, and limited search. Uses stealth headers for
anti-bot evasion. Supports: business profiles, public pages, search (limited).
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

NEXTDOOR_BASE = "https://nextdoor.com"


class NextdoorScraper(BaseScraper):
    """Nextdoor scraper for publicly accessible content.

    Most Nextdoor content is location-gated and requires authentication.
    This scraper handles the publicly accessible portions: business pages,
    public agency pages, and limited search results.

    Usage:
        scraper = NextdoorScraper()
        results = await scraper.scrape_profile("business/some-business-123")
        results = await scraper.scrape_posts("business/some-business-123", max_results=20)
        results = await scraper.search("plumber near me", max_results=10)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()
        self._stealth_client = None

    @property
    def platform_name(self) -> str:
        return "nextdoor"

    async def get_client(self):
        """Override to use stealth headers."""
        if self._stealth_client is None or self._stealth_client.is_closed:
            self._stealth_client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
        return self._stealth_client

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Nextdoor business or public agency profile.

        Args:
            identifier: Business page path (e.g., "business/joes-plumbing-123"),
                        full URL, or business name slug.
        """
        page_url = self._build_page_url(identifier)

        resp = await self.fetch(page_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try embedded structured data first
        page_data = self._extract_page_data(resp.text)
        if page_data:
            profile = self._extract_profile_from_data(page_data)
            if profile:
                profile["page_url"] = page_url
                return [self.make_result(ContentType.PROFILE, profile, url=page_url)]

        # Try JSON-LD structured data (Nextdoor uses this for business pages)
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            profile = self._extract_profile_from_json_ld(json_ld)
            if profile:
                profile["page_url"] = page_url
                return [self.make_result(ContentType.PROFILE, profile, url=page_url)]

        # Fallback to HTML meta tags and page structure
        profile = self._extract_profile_from_html(soup, page_url)
        return [self.make_result(ContentType.PROFILE, profile, url=page_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a Nextdoor business or public page.

        Note: Most neighborhood posts require authentication. This method
        returns publicly visible posts from business pages.

        Args:
            source: Business page path, URL, or identifier.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        page_url = self._build_page_url(source)

        resp = await self.fetch(page_url)

        # Try embedded data
        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = self._extract_posts_from_data(page_data, limit)
            if results:
                return results

        # Fallback: parse posts from HTML
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_posts_from_html(soup, limit)

    async def scrape_business(self, business_url: str) -> list[ScraperResult]:
        """Scrape detailed business information from a Nextdoor business page.

        Extracts business details including name, category, address,
        phone, hours, ratings, and recommendations.

        Args:
            business_url: Full URL to the Nextdoor business page.
        """
        resp = await self.fetch(business_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract comprehensive business data
        json_ld = self._extract_json_ld(soup)
        page_data = self._extract_page_data(resp.text)

        business = self._build_business_profile(soup, json_ld, page_data, business_url)
        return [self.make_result(ContentType.PROFILE, business, url=business_url)]

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Nextdoor for businesses and public pages.

        Note: Full neighborhood search requires authentication. This
        searches publicly accessible business listings.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Try the business search/find endpoint
        results = await self._search_businesses(query, limit)
        if results:
            return results

        # Try the public search page
        return await self._search_public(query, limit)

    async def scrape_public_agency(self, agency_url: str) -> list[ScraperResult]:
        """Scrape a public agency page on Nextdoor.

        Public agencies (police, fire departments, city agencies) have
        publicly viewable pages on Nextdoor.

        Args:
            agency_url: Full URL to the agency page.
        """
        resp = await self.fetch(agency_url)
        soup = BeautifulSoup(resp.text, "lxml")

        page_data = self._extract_page_data(resp.text)
        json_ld = self._extract_json_ld(soup)

        # Extract agency profile
        agency = {
            "name": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
            "url": agency_url,
            "type": "public_agency",
        }

        if json_ld:
            if isinstance(json_ld, dict):
                agency["name"] = json_ld.get("name", agency["name"])
                agency["description"] = json_ld.get("description", agency["description"])
                address = json_ld.get("address", {})
                if isinstance(address, dict):
                    agency["address"] = self._format_address(address)

        if page_data:
            agency_data = self._find_nested(page_data, "agency") or self._find_nested(page_data, "organization")
            if agency_data and isinstance(agency_data, dict):
                agency["name"] = agency_data.get("name", agency["name"])
                agency["follower_count"] = agency_data.get("followerCount", 0)
                agency["post_count"] = agency_data.get("postCount", 0)

        results = [self.make_result(ContentType.PROFILE, agency, url=agency_url)]

        # Also extract any public posts from the agency
        if page_data:
            posts = self._extract_posts_from_data(page_data, 20)
            results.extend(posts)

        return results

    # --- Search methods ---

    async def _search_businesses(self, query: str, limit: int) -> list[ScraperResult]:
        """Search for businesses on Nextdoor."""
        search_url = f"{NEXTDOOR_BASE}/find/{quote(query)}"

        try:
            resp = await self.fetch(search_url)
        except Exception as e:
            logger.debug(f"Business search fetch failed: {e}")
            return []

        # Try embedded data
        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = self._extract_businesses_from_data(page_data, limit)
            if results:
                return results

        # Parse from HTML
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_businesses_from_html(soup, limit)

    async def _search_public(self, query: str, limit: int) -> list[ScraperResult]:
        """Search Nextdoor public pages."""
        search_url = f"{NEXTDOOR_BASE}/search/?query={quote(query)}"

        try:
            resp = await self.fetch(search_url)
        except Exception as e:
            logger.debug(f"Public search fetch failed: {e}")
            return []

        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = []
            # Look for search results in the data
            search_results = self._find_nested(page_data, "searchResults")
            if isinstance(search_results, list):
                for item in search_results:
                    if len(results) >= limit:
                        break
                    if isinstance(item, dict):
                        result_data = self._normalize_search_result(item)
                        if result_data:
                            results.append(
                                self.make_result(
                                    ContentType.SEARCH,
                                    result_data,
                                    url=result_data.get("url", ""),
                                )
                            )
            if results:
                return results

        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_search_from_html(soup, limit)

    # --- Data extraction ---

    def _extract_page_data(self, html: str) -> dict | None:
        """Extract embedded JSON data from a Nextdoor page.

        Nextdoor embeds page data in various script patterns including
        __NEXT_DATA__ and inline JSON state.
        """
        # Pattern 1: Next.js data
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*(\{.+?\})\s*</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Pattern 2: Inline state
        for pattern in [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;',
            r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\})\s*;',
            r'window\.__NEXT_DATA__\s*=\s*(\{.+?\})\s*;',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Pattern 3: Nextdoor-specific data scripts
        match = re.search(
            r'<script[^>]*>\s*window\.__nd\s*=\s*(\{.+?\})\s*;?\s*</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | list | None:
        """Extract JSON-LD structured data from the page."""
        all_ld = []
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    all_ld.append(data)
                except json.JSONDecodeError:
                    continue

        if len(all_ld) == 1:
            return all_ld[0]
        elif all_ld:
            return all_ld
        return None

    def _extract_profile_from_data(self, data: dict) -> dict | None:
        """Extract profile/business data from embedded page JSON."""
        # Navigate common data structures
        page_props = data.get("props", {}).get("pageProps", {})

        # Look for business data
        business = (
            page_props.get("business")
            or page_props.get("businessProfile")
            or page_props.get("profile")
            or self._find_nested(data, "business")
        )

        if business and isinstance(business, dict):
            return self._normalize_business(business)

        # Look for a generic page profile
        page = page_props.get("page") or page_props.get("agency")
        if page and isinstance(page, dict):
            return {
                "name": page.get("name", ""),
                "description": page.get("description", ""),
                "type": page.get("type", "page"),
                "follower_count": page.get("followerCount", 0),
                "image": page.get("image", "") or page.get("logo", ""),
            }

        return None

    def _extract_profile_from_json_ld(self, json_ld: dict | list) -> dict | None:
        """Extract profile data from JSON-LD structured data."""
        if isinstance(json_ld, list):
            for item in json_ld:
                result = self._extract_profile_from_json_ld(item)
                if result:
                    return result
            return None

        ld_type = json_ld.get("@type", "")
        if ld_type in ("LocalBusiness", "Organization", "Store", "Restaurant",
                        "HomeAndConstructionBusiness", "ProfessionalService"):
            address = json_ld.get("address", {})
            aggregate_rating = json_ld.get("aggregateRating", {})

            return {
                "name": json_ld.get("name", ""),
                "description": json_ld.get("description", ""),
                "business_type": ld_type,
                "address": self._format_address(address) if isinstance(address, dict) else str(address),
                "phone": json_ld.get("telephone", ""),
                "url": json_ld.get("url", ""),
                "website": json_ld.get("sameAs", "") or json_ld.get("url", ""),
                "image": json_ld.get("image", ""),
                "rating": aggregate_rating.get("ratingValue") if isinstance(aggregate_rating, dict) else None,
                "review_count": aggregate_rating.get("reviewCount", 0) if isinstance(aggregate_rating, dict) else 0,
                "price_range": json_ld.get("priceRange", ""),
                "hours": self._extract_hours_from_ld(json_ld),
            }

        return None

    def _extract_profile_from_html(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract profile data from HTML meta tags and page elements."""
        profile = {
            "name": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
            "page_url": url,
            "type": self._meta(soup, "og:type") or "page",
        }

        # Try to find business-specific elements
        rating_el = soup.find(class_=re.compile(r"rating|stars"))
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            match = re.search(r'([\d.]+)', rating_text)
            if match:
                profile["rating"] = float(match.group(1))

        address_el = soup.find(class_=re.compile(r"address|location"))
        if address_el:
            profile["address"] = address_el.get_text(strip=True)

        phone_el = soup.find("a", href=re.compile(r"^tel:"))
        if phone_el:
            profile["phone"] = phone_el.get_text(strip=True)

        # Look for recommendation/review count
        rec_el = soup.find(class_=re.compile(r"recommend|review"))
        if rec_el:
            text = rec_el.get_text(strip=True)
            match = re.search(r'(\d+)', text)
            if match:
                profile["recommendation_count"] = int(match.group(1))

        # Business categories
        cat_els = soup.find_all(class_=re.compile(r"category|tag"))
        categories = []
        for el in cat_els:
            text = el.get_text(strip=True)
            if text and len(text) < 100:
                categories.append(text)
        if categories:
            profile["categories"] = categories

        return profile

    def _extract_posts_from_data(self, data: dict, limit: int) -> list[ScraperResult]:
        """Extract posts from embedded page data."""
        results = []

        # Navigate to post collections
        page_props = data.get("props", {}).get("pageProps", {})
        posts = (
            page_props.get("posts", [])
            or page_props.get("updates", [])
            or self._find_nested_list(data, "posts")
            or self._find_nested_list(data, "updates")
            or []
        )

        for post_data in posts:
            if len(results) >= limit:
                break
            if not isinstance(post_data, dict):
                continue

            post = self._normalize_post(post_data)
            if post:
                results.append(
                    self.make_result(ContentType.POST, post, url=post.get("url", ""))
                )

        return results

    def _extract_posts_from_html(self, soup: BeautifulSoup, limit: int) -> list[ScraperResult]:
        """Extract posts from HTML page structure."""
        results = []

        # Look for post/update card elements
        for card in soup.find_all(
            ["article", "div"],
            class_=re.compile(r"post-card|update-card|feed-item|content-card"),
        ):
            if len(results) >= limit:
                break

            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else ""

            body_el = card.find(class_=re.compile(r"body|content|text|message"))
            body = body_el.get_text(strip=True) if body_el else ""

            if not title and not body:
                continue

            link = card.find("a", href=True)
            href = ""
            if link:
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{NEXTDOOR_BASE}{href}"

            author_el = card.find(class_=re.compile(r"author|business-name|name"))
            author = author_el.get_text(strip=True) if author_el else ""

            date_el = card.find(class_=re.compile(r"date|time|timestamp"))
            date = date_el.get_text(strip=True) if date_el else ""

            img = card.find("img", src=True)
            image = img["src"] if img else ""

            post = {
                "title": title,
                "body": body,
                "author": author,
                "date": date,
                "image": image,
                "url": href,
            }
            results.append(self.make_result(ContentType.POST, post, url=href))

        return results

    def _extract_businesses_from_data(self, data: dict, limit: int) -> list[ScraperResult]:
        """Extract business listing results from embedded page data."""
        results = []

        page_props = data.get("props", {}).get("pageProps", {})
        businesses = (
            page_props.get("businesses", [])
            or page_props.get("results", [])
            or self._find_nested_list(data, "businesses")
            or self._find_nested_list(data, "results")
            or []
        )

        for biz in businesses:
            if len(results) >= limit:
                break
            if not isinstance(biz, dict):
                continue

            business = self._normalize_business(biz)
            if business:
                results.append(
                    self.make_result(
                        ContentType.SEARCH, business, url=business.get("page_url", "")
                    )
                )

        return results

    def _extract_businesses_from_html(
        self, soup: BeautifulSoup, limit: int
    ) -> list[ScraperResult]:
        """Extract business listings from HTML search results."""
        results = []

        for card in soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"business-card|search-result|listing"),
        ):
            if len(results) >= limit:
                break

            name_el = card.find(["h2", "h3", "a"], class_=re.compile(r"name|title"))
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue

            link = card.find("a", href=True)
            href = ""
            if link:
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{NEXTDOOR_BASE}{href}"

            cat_el = card.find(class_=re.compile(r"category|type"))
            category = cat_el.get_text(strip=True) if cat_el else ""

            rating_el = card.find(class_=re.compile(r"rating|stars"))
            rating = None
            if rating_el:
                match = re.search(r'([\d.]+)', rating_el.get_text(strip=True))
                if match:
                    rating = float(match.group(1))

            rec_el = card.find(class_=re.compile(r"recommend|review|count"))
            rec_count = 0
            if rec_el:
                match = re.search(r'(\d+)', rec_el.get_text(strip=True))
                if match:
                    rec_count = int(match.group(1))

            address_el = card.find(class_=re.compile(r"address|location"))
            address = address_el.get_text(strip=True) if address_el else ""

            business = {
                "name": name,
                "category": category,
                "rating": rating,
                "recommendation_count": rec_count,
                "address": address,
                "page_url": href,
            }
            results.append(self.make_result(ContentType.SEARCH, business, url=href))

        return results

    def _extract_search_from_html(
        self, soup: BeautifulSoup, limit: int
    ) -> list[ScraperResult]:
        """Extract generic search results from HTML."""
        results = []

        for link in soup.find_all("a", href=True):
            if len(results) >= limit:
                break

            href = link.get("href", "")
            # Only interested in Nextdoor content links
            if not any(seg in href for seg in ("/business/", "/agency/", "/pages/", "/find/")):
                continue

            if not href.startswith("http"):
                href = f"{NEXTDOOR_BASE}{href}"

            title = link.get_text(strip=True)
            if not title or len(title) < 3 or len(title) > 200:
                continue

            result = {
                "title": title,
                "url": href,
            }
            results.append(self.make_result(ContentType.SEARCH, result, url=href))

        return results

    # --- Data normalization ---

    def _normalize_business(self, data: dict) -> dict | None:
        """Normalize a business data dict."""
        name = data.get("name", "") or data.get("businessName", "")
        if not name:
            return None

        # Handle address
        address_data = data.get("address", {})
        if isinstance(address_data, dict):
            address = self._format_address(address_data)
        elif isinstance(address_data, str):
            address = address_data
        else:
            address = ""

        # Handle rating
        rating = data.get("rating")
        if isinstance(rating, dict):
            rating = rating.get("value") or rating.get("average")

        # Build page URL
        slug = data.get("slug", "") or data.get("permalink", "") or data.get("id", "")
        page_url = f"{NEXTDOOR_BASE}/business/{slug}" if slug else ""

        return {
            "name": name,
            "category": data.get("category", "") or data.get("businessCategory", ""),
            "description": data.get("description", "") or data.get("about", ""),
            "address": address,
            "phone": data.get("phone", "") or data.get("phoneNumber", ""),
            "website": data.get("website", "") or data.get("websiteUrl", ""),
            "rating": rating,
            "recommendation_count": (
                data.get("recommendationCount", 0)
                or data.get("endorsementCount", 0)
                or data.get("reviewCount", 0)
            ),
            "is_claimed": data.get("isClaimed", False),
            "is_verified": data.get("isVerified", False),
            "image": data.get("image", "") or data.get("logo", "") or data.get("photoUrl", ""),
            "hours": data.get("hours", []) or data.get("businessHours", []),
            "page_url": page_url,
        }

    def _normalize_post(self, data: dict) -> dict | None:
        """Normalize a post/update data dict."""
        body = data.get("body", "") or data.get("text", "") or data.get("content", "")
        title = data.get("title", "") or data.get("subject", "")

        if not body and not title:
            return None

        author = data.get("author", {})
        if isinstance(author, dict):
            author_name = author.get("name", "") or author.get("displayName", "")
        elif isinstance(author, str):
            author_name = author
        else:
            author_name = ""

        post_id = data.get("id", "") or data.get("postId", "")
        post_url = ""
        if post_id:
            post_url = f"{NEXTDOOR_BASE}/p/{post_id}"

        # Extract images
        images = []
        media = data.get("media", []) or data.get("photos", []) or data.get("images", [])
        if isinstance(media, list):
            for item in media:
                if isinstance(item, dict):
                    url = item.get("url", "") or item.get("src", "")
                    if url:
                        images.append(url)
                elif isinstance(item, str):
                    images.append(item)

        return {
            "post_id": str(post_id),
            "title": title,
            "body": body,
            "author": author_name,
            "images": images,
            "like_count": data.get("likeCount", 0) or data.get("reactions", 0),
            "comment_count": data.get("commentCount", 0) or data.get("replyCount", 0),
            "created_at": data.get("createdAt", "") or data.get("publishedAt", ""),
            "url": data.get("url", post_url),
            "type": data.get("type", "update"),
        }

    def _normalize_search_result(self, data: dict) -> dict | None:
        """Normalize a search result item."""
        result_type = data.get("type", "") or data.get("kind", "")
        title = data.get("title", "") or data.get("name", "")
        if not title:
            return None

        href = data.get("url", "") or data.get("permalink", "")
        if href and not href.startswith("http"):
            href = f"{NEXTDOOR_BASE}{href}"

        return {
            "title": title,
            "description": data.get("description", "") or data.get("snippet", ""),
            "type": result_type,
            "url": href,
            "image": data.get("image", "") or data.get("thumbnail", ""),
        }

    def _build_business_profile(
        self,
        soup: BeautifulSoup,
        json_ld: dict | list | None,
        page_data: dict | None,
        url: str,
    ) -> dict:
        """Build a comprehensive business profile from all available data sources."""
        # Start with HTML data
        profile = self._extract_profile_from_html(soup, url)

        # Enrich with JSON-LD
        if json_ld:
            ld_profile = self._extract_profile_from_json_ld(json_ld)
            if ld_profile:
                for key, value in ld_profile.items():
                    if value and not profile.get(key):
                        profile[key] = value

        # Enrich with embedded page data
        if page_data:
            data_profile = self._extract_profile_from_data(page_data)
            if data_profile:
                for key, value in data_profile.items():
                    if value and not profile.get(key):
                        profile[key] = value

        # Extract reviews/recommendations from HTML
        reviews = self._extract_reviews_from_html(soup)
        if reviews:
            profile["recent_reviews"] = reviews[:5]

        return profile

    def _extract_reviews_from_html(self, soup: BeautifulSoup) -> list[dict]:
        """Extract reviews/recommendations from a business page."""
        reviews = []

        for review_el in soup.find_all(
            ["div", "article"],
            class_=re.compile(r"review|recommendation|endorsement"),
        ):
            author_el = review_el.find(class_=re.compile(r"author|name|reviewer"))
            author = author_el.get_text(strip=True) if author_el else ""

            body_el = review_el.find(class_=re.compile(r"body|text|content|comment"))
            body = body_el.get_text(strip=True) if body_el else review_el.get_text(strip=True)

            date_el = review_el.find(class_=re.compile(r"date|time"))
            date = date_el.get_text(strip=True) if date_el else ""

            if body and len(body) > 10:
                reviews.append({
                    "author": author,
                    "body": body[:500],
                    "date": date,
                })

        return reviews

    # --- Utility methods ---

    def _build_page_url(self, identifier: str) -> str:
        """Build a Nextdoor page URL from an identifier."""
        if identifier.startswith("http"):
            return identifier

        # Clean up the identifier
        identifier = identifier.strip("/")

        # Check if it already has a path prefix
        if identifier.startswith(("business/", "agency/", "pages/")):
            return f"{NEXTDOOR_BASE}/{identifier}"

        # Default to business page
        return f"{NEXTDOOR_BASE}/business/{identifier}"

    @staticmethod
    def _format_address(address: dict) -> str:
        """Format a JSON-LD address object into a string."""
        parts = []
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
            val = address.get(key, "")
            if val:
                parts.append(str(val))
        return ", ".join(parts)

    @staticmethod
    def _extract_hours_from_ld(json_ld: dict) -> list[dict]:
        """Extract business hours from JSON-LD data."""
        hours = []
        opening_hours = json_ld.get("openingHoursSpecification", [])
        if isinstance(opening_hours, list):
            for spec in opening_hours:
                if isinstance(spec, dict):
                    day = spec.get("dayOfWeek", "")
                    if isinstance(day, list):
                        day = ", ".join(day)
                    hours.append({
                        "day": day,
                        "opens": spec.get("opens", ""),
                        "closes": spec.get("closes", ""),
                    })
        return hours

    def _find_nested(self, data: Any, key: str) -> Any:
        """Find a key in nested dict structure."""
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for value in data.values():
                result = self._find_nested(value, key)
                if result is not None:
                    return result
        return None

    def _find_nested_list(self, data: Any, key: str) -> list | None:
        """Find a list value by key in nested dict structure."""
        result = self._find_nested(data, key)
        if isinstance(result, list):
            return result
        return None

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return tag.get("content", "") if tag else ""

    async def close(self):
        """Close the stealth client and base client."""
        if self._stealth_client and not self._stealth_client.is_closed:
            await self._stealth_client.aclose()
        await super().close()
