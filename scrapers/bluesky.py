"""Bluesky scraper using the AT Protocol public API.

No API key required for public data. Bluesky is designed for open data access.
Supports: profiles, posts, feeds, search.
"""

import logging
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

# Bluesky public API (no auth needed for public data)
BSKY_PUBLIC_API = "https://public.api.bsky.app"


class BlueskyScraper(BaseScraper):
    """Bluesky scraper using the AT Protocol public API.

    No authentication required for public profiles and posts.

    Usage:
        scraper = BlueskyScraper()
        results = await scraper.scrape_profile("jay.bsky.team")
        results = await scraper.scrape_posts("jay.bsky.team", max_results=50)
        results = await scraper.search("python", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "bluesky"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Bluesky profile.

        Args:
            identifier: DID or handle (e.g. "jay.bsky.team").
        """
        handle = self._normalize_handle(identifier)
        url = f"{BSKY_PUBLIC_API}/xrpc/app.bsky.actor.getProfile"

        data = await self.fetch_json(url, params={"actor": handle})

        profile = {
            "did": data.get("did", ""),
            "handle": data.get("handle", ""),
            "display_name": data.get("displayName", ""),
            "description": data.get("description", ""),
            "avatar": data.get("avatar", ""),
            "banner": data.get("banner", ""),
            "followers_count": data.get("followersCount", 0),
            "following_count": data.get("followsCount", 0),
            "posts_count": data.get("postsCount", 0),
            "created_at": data.get("createdAt", ""),
            "labels": [l.get("val", "") for l in data.get("labels", [])],
            "profile_url": f"https://bsky.app/profile/{data.get('handle', handle)}",
        }

        return [
            self.make_result(
                ContentType.PROFILE,
                profile,
                url=f"https://bsky.app/profile/{handle}",
            )
        ]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a Bluesky user's feed.

        Args:
            source: Handle or DID.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        handle = self._normalize_handle(source)
        url = f"{BSKY_PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed"

        results = []
        cursor = None

        while len(results) < limit:
            params = {
                "actor": handle,
                "limit": min(100, limit - len(results)),
            }
            if cursor:
                params["cursor"] = cursor

            data = await self.fetch_json(url, params=params)
            feed = data.get("feed", [])

            if not feed:
                break

            for item in feed:
                if len(results) >= limit:
                    break
                post = item.get("post", {})
                post_data = self._extract_post_data(post)
                # Add repost info
                reason = item.get("reason")
                if reason and reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
                    post_data["is_repost"] = True
                    post_data["reposted_by"] = reason.get("by", {}).get("handle", "")

                results.append(
                    self.make_result(ContentType.POST, post_data, url=post_data.get("url", ""))
                )

            cursor = data.get("cursor")
            if not cursor:
                break

        return results

    async def scrape_thread(self, post_uri: str) -> list[ScraperResult]:
        """Scrape a full thread (post + replies).

        Args:
            post_uri: AT-URI of the post (at://did/app.bsky.feed.post/rkey).
        """
        url = f"{BSKY_PUBLIC_API}/xrpc/app.bsky.feed.getPostThread"
        data = await self.fetch_json(url, params={"uri": post_uri, "depth": 10})

        results = []
        thread = data.get("thread", {})
        self._flatten_thread(thread, results)

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Bluesky posts.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        url = f"{BSKY_PUBLIC_API}/xrpc/app.bsky.feed.searchPosts"

        results = []
        cursor = None

        while len(results) < limit:
            params = {
                "q": query,
                "limit": min(100, limit - len(results)),
            }
            if cursor:
                params["cursor"] = cursor

            data = await self.fetch_json(url, params=params)
            posts = data.get("posts", [])

            if not posts:
                break

            for post in posts:
                if len(results) >= limit:
                    break
                post_data = self._extract_post_data(post)
                results.append(
                    self.make_result(ContentType.SEARCH, post_data, url=post_data.get("url", ""))
                )

            cursor = data.get("cursor")
            if not cursor:
                break

        return results

    async def search_users(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Bluesky users.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        url = f"{BSKY_PUBLIC_API}/xrpc/app.bsky.actor.searchActors"

        params = {"q": query, "limit": min(100, limit)}
        data = await self.fetch_json(url, params=params)

        results = []
        for actor in data.get("actors", [])[:limit]:
            profile = {
                "did": actor.get("did", ""),
                "handle": actor.get("handle", ""),
                "display_name": actor.get("displayName", ""),
                "description": actor.get("description", ""),
                "avatar": actor.get("avatar", ""),
                "followers_count": actor.get("followersCount", 0),
                "following_count": actor.get("followsCount", 0),
                "posts_count": actor.get("postsCount", 0),
            }
            results.append(
                self.make_result(
                    ContentType.PROFILE,
                    profile,
                    url=f"https://bsky.app/profile/{actor.get('handle', '')}",
                )
            )

        return results

    def _normalize_handle(self, identifier: str) -> str:
        if identifier.startswith("http"):
            # Extract handle from bsky.app URL
            parts = identifier.rstrip("/").split("/")
            return parts[-1] if parts else identifier
        if identifier.startswith("@"):
            return identifier[1:]
        return identifier

    def _extract_post_data(self, post: dict) -> dict[str, Any]:
        record = post.get("record", {})
        author = post.get("author", {})

        # Build the bsky.app URL
        uri = post.get("uri", "")
        handle = author.get("handle", "")
        rkey = uri.split("/")[-1] if uri else ""
        post_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else ""

        # Extract images
        images = []
        embed = post.get("embed", {})
        if embed.get("$type") == "app.bsky.embed.images#view":
            for img in embed.get("images", []):
                images.append({
                    "thumb": img.get("thumb", ""),
                    "fullsize": img.get("fullsize", ""),
                    "alt": img.get("alt", ""),
                })

        # Extract external link
        external = None
        if embed.get("$type") == "app.bsky.embed.external#view":
            ext = embed.get("external", {})
            external = {
                "uri": ext.get("uri", ""),
                "title": ext.get("title", ""),
                "description": ext.get("description", ""),
            }

        return {
            "uri": uri,
            "cid": post.get("cid", ""),
            "author_handle": handle,
            "author_display_name": author.get("displayName", ""),
            "author_did": author.get("did", ""),
            "text": record.get("text", ""),
            "created_at": record.get("createdAt", ""),
            "like_count": post.get("likeCount", 0),
            "repost_count": post.get("repostCount", 0),
            "reply_count": post.get("replyCount", 0),
            "quote_count": post.get("quoteCount", 0),
            "images": images,
            "external_link": external,
            "labels": [l.get("val", "") for l in post.get("labels", [])],
            "is_repost": False,
            "url": post_url,
        }

    def _flatten_thread(self, thread: dict, results: list[ScraperResult], depth: int = 0):
        if not isinstance(thread, dict):
            return
        if thread.get("$type") == "app.bsky.feed.defs#blockedPost":
            return

        post = thread.get("post")
        if post:
            post_data = self._extract_post_data(post)
            post_data["thread_depth"] = depth
            results.append(
                self.make_result(ContentType.POST, post_data, url=post_data.get("url", ""))
            )

        for reply in thread.get("replies", []):
            self._flatten_thread(reply, results, depth + 1)
