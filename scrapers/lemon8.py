"""Lemon8 scraper using web scraping with stealth headers.

No API key required. Scrapes public Lemon8 pages and parses structured data
from embedded JSON and HTML. Lemon8 is a lifestyle content platform by
ByteDance. Supports: user profiles, posts, search.
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

LEMON8_BASE = "https://www.lemon8-app.com"


class Lemon8Scraper(BaseScraper):
    """Lemon8 scraper using stealth web scraping.

    No authentication needed. Parses publicly available Lemon8 pages
    and extracts structured data from embedded JSON and HTML elements.

    Usage:
        scraper = Lemon8Scraper()
        results = await scraper.scrape_profile("username")
        results = await scraper.scrape_posts("username", max_results=20)
        results = await scraper.search("skincare routine", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()
        self._stealth_client = None

    @property
    def platform_name(self) -> str:
        return "lemon8"

    async def get_client(self):
        """Override to use stealth headers."""
        if self._stealth_client is None or self._stealth_client.is_closed:
            self._stealth_client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
        return self._stealth_client

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Lemon8 user profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        profile_url = f"{LEMON8_BASE}/{username}"

        resp = await self.fetch(profile_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try to extract structured data from embedded JSON
        page_data = self._extract_page_data(resp.text)

        if page_data:
            profile = self._extract_profile_from_data(page_data, username)
            if profile:
                profile["profile_url"] = profile_url
                return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

        # Try JSON-LD structured data
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            profile = self._extract_profile_from_json_ld(json_ld, username)
            if profile:
                profile["profile_url"] = profile_url
                return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

        # Fallback to HTML meta tags and page structure
        profile = self._extract_profile_from_html(soup, username, profile_url)
        return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a Lemon8 user.

        Args:
            source: Username or profile URL.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        profile_url = f"{LEMON8_BASE}/{username}"

        resp = await self.fetch(profile_url)

        # Try embedded page data first
        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = self._extract_posts_from_data(page_data, username, limit)
            if results:
                return results

        # Fallback: parse posts from HTML
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_posts_from_html(soup, username, limit)

    async def scrape_post(self, post_url: str) -> list[ScraperResult]:
        """Scrape a single Lemon8 post.

        Args:
            post_url: Full URL to the post.
        """
        resp = await self.fetch(post_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Try embedded data
        page_data = self._extract_page_data(resp.text)
        if page_data:
            post = self._extract_single_post_from_data(page_data, post_url)
            if post:
                return [self.make_result(ContentType.POST, post, url=post_url)]

        # Try JSON-LD
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            post = self._extract_post_from_json_ld(json_ld, post_url)
            if post:
                return [self.make_result(ContentType.POST, post, url=post_url)]

        # Fallback: HTML parsing
        post = self._extract_post_from_html(soup, post_url)
        return [self.make_result(ContentType.POST, post, url=post_url)]

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Lemon8 for posts.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Lemon8 search page
        search_url = f"{LEMON8_BASE}/search?q={quote(query)}"

        try:
            resp = await self.fetch(search_url)
        except Exception as e:
            logger.warning(f"Search page fetch failed: {e}")
            # Try alternative search URL patterns
            search_url = f"{LEMON8_BASE}/discover/{quote(query)}"
            resp = await self.fetch(search_url)

        # Try embedded data
        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = self._extract_search_results_from_data(page_data, limit)
            if results:
                return results

        # Fallback: parse search results HTML
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_search_results_from_html(soup, limit)

    async def scrape_discover(self, max_results: int | None = None) -> list[ScraperResult]:
        """Scrape the Lemon8 discover/trending page.

        Args:
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        discover_url = f"{LEMON8_BASE}/discover"

        resp = await self.fetch(discover_url)

        page_data = self._extract_page_data(resp.text)
        if page_data:
            results = self._extract_search_results_from_data(page_data, limit)
            if results:
                return results

        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_posts_from_html(soup, "", limit, content_type=ContentType.TRENDING)

    # --- Data extraction ---

    def _extract_page_data(self, html: str) -> dict | None:
        """Extract embedded JSON data from a Lemon8 page.

        Lemon8 (ByteDance) typically embeds page data in script tags
        using patterns like __INITIAL_STATE__, __NEXT_DATA__, or similar.
        """
        # Pattern 1: Next.js-style __NEXT_DATA__
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

        # Pattern 2: __INITIAL_STATE__ or similar ByteDance patterns
        for pattern in [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;',
            r'window\.__INITIAL_PROPS__\s*=\s*(\{.+?\})\s*;',
            r'window\.__data\s*=\s*(\{.+?\})\s*;',
            r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\})\s*;',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Pattern 3: Generic application/json script tags with data
        for match in re.finditer(
            r'<script[^>]*type="application/json"[^>]*>\s*(\{.+?\})\s*</script>',
            html,
            re.DOTALL,
        ):
            try:
                data = json.loads(match.group(1))
                # Only accept if it has substantial content
                if len(str(data)) > 200:
                    return data
            except json.JSONDecodeError:
                continue

        return None

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Extract JSON-LD structured data from the page."""
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    return data
                except json.JSONDecodeError:
                    continue
        return None

    def _extract_profile_from_data(self, data: dict, username: str) -> dict | None:
        """Extract profile data from embedded page JSON."""
        # Walk the data looking for user/profile objects
        user = self._find_nested_user(data)
        if not user:
            return None

        return {
            "user_id": user.get("uid", "") or user.get("id", "") or user.get("user_id", ""),
            "username": user.get("unique_id", "") or user.get("username", username),
            "display_name": user.get("nickname", "") or user.get("name", ""),
            "bio": user.get("signature", "") or user.get("bio", "") or user.get("description", ""),
            "avatar_url": user.get("avatar_url", "") or user.get("avatar", ""),
            "follower_count": user.get("follower_count", 0),
            "following_count": user.get("following_count", 0),
            "like_count": user.get("total_favorited", 0) or user.get("like_count", 0),
            "post_count": user.get("aweme_count", 0) or user.get("post_count", 0),
            "verified": user.get("verified", False),
        }

    def _extract_profile_from_json_ld(self, json_ld: dict | list, username: str) -> dict | None:
        """Extract profile data from JSON-LD structured data."""
        if isinstance(json_ld, list):
            for item in json_ld:
                result = self._extract_profile_from_json_ld(item, username)
                if result:
                    return result
            return None

        ld_type = json_ld.get("@type", "")
        if ld_type in ("Person", "ProfilePage"):
            return {
                "username": json_ld.get("alternateName", username),
                "display_name": json_ld.get("name", ""),
                "bio": json_ld.get("description", ""),
                "avatar_url": json_ld.get("image", ""),
                "url": json_ld.get("url", ""),
            }

        # Check for mainEntity
        main = json_ld.get("mainEntity")
        if isinstance(main, dict):
            return self._extract_profile_from_json_ld(main, username)

        return None

    def _extract_profile_from_html(
        self, soup: BeautifulSoup, username: str, url: str
    ) -> dict:
        """Extract profile data from HTML meta tags and page elements."""
        profile = {
            "username": username,
            "display_name": self._meta(soup, "og:title") or username,
            "bio": self._meta(soup, "og:description") or "",
            "avatar_url": self._meta(soup, "og:image") or "",
            "profile_url": url,
        }

        # Try to extract stats from page elements
        for el in soup.find_all(class_=re.compile(r"follower|follow-count")):
            text = el.get_text(strip=True)
            count = self._parse_count(text)
            if count is not None:
                if "follower" in (el.get("class", [""])[0] if el.get("class") else "").lower():
                    profile["follower_count"] = count

        return profile

    def _extract_posts_from_data(
        self, data: dict, username: str, limit: int
    ) -> list[ScraperResult]:
        """Extract posts from embedded page data."""
        results = []
        posts = self._find_posts_in_data(data)

        for post_data in posts:
            if len(results) >= limit:
                break
            post = self._normalize_post(post_data, username)
            if post:
                results.append(
                    self.make_result(ContentType.POST, post, url=post.get("url", ""))
                )

        return results

    def _extract_single_post_from_data(self, data: dict, post_url: str) -> dict | None:
        """Extract a single post from embedded page data."""
        posts = self._find_posts_in_data(data)
        if posts:
            post = self._normalize_post(posts[0], "")
            if post:
                post["url"] = post.get("url") or post_url
                return post

        # Try to find the post at the top level
        item_detail = (
            data.get("props", {}).get("pageProps", {}).get("itemDetail")
            or data.get("itemDetail")
            or data.get("post")
        )
        if item_detail:
            return self._normalize_post(item_detail, "")

        return None

    def _extract_post_from_json_ld(self, json_ld: dict | list, post_url: str) -> dict | None:
        """Extract post data from JSON-LD structured data."""
        if isinstance(json_ld, list):
            for item in json_ld:
                result = self._extract_post_from_json_ld(item, post_url)
                if result:
                    return result
            return None

        ld_type = json_ld.get("@type", "")
        if ld_type in ("Article", "BlogPosting", "SocialMediaPosting", "CreativeWork"):
            author = json_ld.get("author", {})
            if isinstance(author, list):
                author = author[0] if author else {}

            images = []
            img = json_ld.get("image")
            if isinstance(img, str):
                images = [img]
            elif isinstance(img, list):
                images = [i if isinstance(i, str) else i.get("url", "") for i in img]

            return {
                "title": json_ld.get("headline", "") or json_ld.get("name", ""),
                "description": json_ld.get("description", ""),
                "author": author.get("name", "") if isinstance(author, dict) else str(author),
                "published_date": json_ld.get("datePublished", ""),
                "modified_date": json_ld.get("dateModified", ""),
                "images": images,
                "url": json_ld.get("url", post_url),
                "interaction_count": json_ld.get("interactionCount", 0),
            }

        return None

    def _extract_post_from_html(self, soup: BeautifulSoup, post_url: str) -> dict:
        """Extract post data from HTML elements."""
        post = {
            "title": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "image": self._meta(soup, "og:image") or "",
            "url": post_url,
            "author": self._meta(soup, "author") or "",
        }

        # Try to extract the main content
        article = soup.find("article") or soup.find("div", class_=re.compile(r"post-content|article"))
        if article:
            paragraphs = article.find_all(["p", "h1", "h2", "h3"])
            post["content"] = "\n\n".join(
                p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
            )

        # Extract images
        images = []
        if article:
            for img in article.find_all("img", src=True):
                src = img["src"]
                if src and not src.endswith((".svg", ".gif")):
                    images.append(src)
        post["images"] = images

        # Extract tags/hashtags
        tags = []
        for link in soup.find_all("a", href=re.compile(r"/hashtag/|/tag/")):
            tag_text = link.get_text(strip=True).lstrip("#")
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
        post["tags"] = tags

        return post

    def _extract_posts_from_html(
        self,
        soup: BeautifulSoup,
        username: str,
        limit: int,
        content_type: ContentType = ContentType.POST,
    ) -> list[ScraperResult]:
        """Extract posts from HTML page structure."""
        results = []

        # Look for post card elements
        for card in soup.find_all(
            ["article", "div"],
            class_=re.compile(r"post-card|feed-item|note-card|content-card"),
        ):
            if len(results) >= limit:
                break

            link = card.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"{LEMON8_BASE}{href}"

            title_el = card.find(["h2", "h3", "span"], class_=re.compile(r"title|caption"))
            title = title_el.get_text(strip=True) if title_el else ""

            img = card.find("img", src=True)
            image = img["src"] if img else ""

            author_el = card.find(class_=re.compile(r"author|user"))
            author = author_el.get_text(strip=True) if author_el else username

            post = {
                "title": title,
                "url": href,
                "image": image,
                "author": author,
            }
            results.append(self.make_result(content_type, post, url=href))

        # If no cards found, try generic link extraction
        if not results:
            for link in soup.find_all("a", href=re.compile(r"/\d+|/post/")):
                if len(results) >= limit:
                    break

                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{LEMON8_BASE}{href}"

                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                img = link.find("img", src=True)
                image = img["src"] if img else ""

                post = {
                    "title": title,
                    "url": href,
                    "image": image,
                    "author": username,
                }
                results.append(self.make_result(content_type, post, url=href))

        return results

    def _extract_search_results_from_data(
        self, data: dict, limit: int
    ) -> list[ScraperResult]:
        """Extract search results from embedded page data."""
        results = []
        posts = self._find_posts_in_data(data)

        for post_data in posts:
            if len(results) >= limit:
                break
            post = self._normalize_post(post_data, "")
            if post:
                results.append(
                    self.make_result(ContentType.SEARCH, post, url=post.get("url", ""))
                )

        return results

    def _extract_search_results_from_html(
        self, soup: BeautifulSoup, limit: int
    ) -> list[ScraperResult]:
        """Extract search results from HTML."""
        return self._extract_posts_from_html(soup, "", limit, content_type=ContentType.SEARCH)

    # --- Data walking and normalization ---

    def _find_nested_user(self, data: Any) -> dict | None:
        """Recursively search for a user object in nested data."""
        if isinstance(data, dict):
            # Check if this looks like a user object
            if (
                ("uid" in data or "user_id" in data)
                and ("nickname" in data or "unique_id" in data or "username" in data)
            ):
                return data

            # Check common keys
            for key in ("user", "userInfo", "author", "creator", "owner"):
                val = data.get(key)
                if isinstance(val, dict) and (
                    "nickname" in val or "unique_id" in val or "username" in val
                ):
                    return val

            # Recurse into pageProps and other nested structures
            for key in ("props", "pageProps", "data", "userDetail", "userModule"):
                if key in data:
                    result = self._find_nested_user(data[key])
                    if result:
                        return result

        return None

    def _find_posts_in_data(self, data: Any, depth: int = 0) -> list[dict]:
        """Recursively search for post/item collections in nested data."""
        posts = []
        if depth > 8 or not isinstance(data, dict):
            return posts

        # Check for common collection keys
        for key in (
            "itemList", "items", "posts", "notes", "awemeList",
            "feedList", "collection", "results",
        ):
            val = data.get(key)
            if isinstance(val, list) and val:
                for item in val:
                    if isinstance(item, dict) and self._looks_like_post(item):
                        posts.append(item)
                if posts:
                    return posts

        # Recurse into nested structures
        for key in ("props", "pageProps", "data", "state"):
            if key in data:
                nested = self._find_posts_in_data(data[key], depth + 1)
                if nested:
                    return nested

        return posts

    @staticmethod
    def _looks_like_post(item: dict) -> bool:
        """Check if a dict looks like a post/content item."""
        post_keys = {"title", "desc", "caption", "content", "text", "headline"}
        id_keys = {"id", "item_id", "post_id", "aweme_id", "note_id"}
        has_content = bool(post_keys & set(item.keys()))
        has_id = bool(id_keys & set(item.keys()))
        return has_content or has_id

    def _normalize_post(self, post_data: dict, default_author: str) -> dict | None:
        """Normalize a post data dict into a standard format."""
        post_id = (
            post_data.get("id", "")
            or post_data.get("item_id", "")
            or post_data.get("post_id", "")
            or post_data.get("note_id", "")
        )

        title = (
            post_data.get("title", "")
            or post_data.get("desc", "")
            or post_data.get("caption", "")
            or post_data.get("headline", "")
        )

        if not post_id and not title:
            return None

        # Extract author
        author_data = post_data.get("author", {}) or post_data.get("user", {})
        if isinstance(author_data, dict):
            author = (
                author_data.get("unique_id", "")
                or author_data.get("username", "")
                or author_data.get("nickname", "")
                or default_author
            )
        elif isinstance(author_data, str):
            author = author_data
        else:
            author = default_author

        # Extract images
        images = []
        image_list = post_data.get("images", []) or post_data.get("image_list", [])
        if isinstance(image_list, list):
            for img in image_list:
                if isinstance(img, dict):
                    url = img.get("url", "") or img.get("url_list", [""])[0] if img.get("url_list") else ""
                    if url:
                        images.append(url)
                elif isinstance(img, str):
                    images.append(img)

        # Cover image
        cover = post_data.get("cover", {})
        cover_url = ""
        if isinstance(cover, dict):
            cover_url = cover.get("url", "") or (
                cover.get("url_list", [""])[0] if cover.get("url_list") else ""
            )
        elif isinstance(cover, str):
            cover_url = cover

        # Stats
        stats = post_data.get("statistics", {}) or post_data.get("stats", {})

        # Tags
        tags = []
        for tag_item in post_data.get("text_extra", []) or post_data.get("tags", []):
            if isinstance(tag_item, dict):
                tag_name = tag_item.get("hashtag_name", "") or tag_item.get("name", "")
                if tag_name:
                    tags.append(tag_name)
            elif isinstance(tag_item, str):
                tags.append(tag_item)

        return {
            "post_id": str(post_id),
            "title": title,
            "content": post_data.get("content", "") or post_data.get("text", ""),
            "author": author,
            "images": images,
            "cover_image": cover_url,
            "like_count": (
                stats.get("digg_count", 0)
                or stats.get("like_count", 0)
                or post_data.get("digg_count", 0)
            ),
            "comment_count": (
                stats.get("comment_count", 0)
                or post_data.get("comment_count", 0)
            ),
            "share_count": (
                stats.get("share_count", 0)
                or post_data.get("share_count", 0)
            ),
            "collect_count": (
                stats.get("collect_count", 0)
                or post_data.get("collect_count", 0)
            ),
            "tags": tags,
            "created_time": post_data.get("create_time", "") or post_data.get("createTime", ""),
            "url": post_data.get("url", "") or self._build_post_url(author, post_id),
        }

    def _build_post_url(self, username: str, post_id: str) -> str:
        """Build a Lemon8 post URL from username and post ID."""
        if username and post_id:
            return f"{LEMON8_BASE}/{username}/{post_id}"
        return ""

    # --- Utilities ---

    def _normalize_username(self, identifier: str) -> str:
        """Extract a username from various input formats."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            parts = path.split("/")
            return parts[0] if parts else identifier
        return identifier.strip("@/")

    @staticmethod
    def _parse_count(text: str) -> int | None:
        """Parse a human-readable count string (e.g., '1.2K', '3M')."""
        text = text.strip().upper()
        match = re.search(r'([\d.]+)\s*([KMB]?)', text)
        if not match:
            return None

        num = float(match.group(1))
        suffix = match.group(2)
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
        return int(num * multiplier)

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
