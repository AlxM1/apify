"""Hacker News scraper using the free official Firebase API.

No API key required. Official API docs: https://github.com/HackerNewsAPI/API
Supports: stories, comments, profiles, search (via Algolia).
"""

import logging
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

# Official HN Firebase API (free, no auth)
HN_API = "https://hacker-news.firebaseio.com/v0"
# Algolia HN Search API (free, no auth)
ALGOLIA_API = "https://hn.algolia.com/api/v1"


class HackerNewsScraper(BaseScraper):
    """Hacker News scraper using the official API + Algolia search.

    Both APIs are completely free with no authentication required.

    Usage:
        scraper = HackerNewsScraper()
        results = await scraper.scrape_profile("pg")
        results = await scraper.scrape_posts("top", max_results=30)
        results = await scraper.search("python web scraping", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "hackernews"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Hacker News user profile.

        Args:
            identifier: HN username.
        """
        url = f"{HN_API}/user/{identifier}.json"
        data = await self.fetch_json(url)

        if not data:
            return []

        profile = {
            "username": data.get("id", identifier),
            "karma": data.get("karma", 0),
            "about": data.get("about", ""),
            "created": data.get("created"),
            "submitted_count": len(data.get("submitted", [])),
            "profile_url": f"https://news.ycombinator.com/user?id={identifier}",
        }

        return [
            self.make_result(
                ContentType.PROFILE,
                profile,
                url=f"https://news.ycombinator.com/user?id={identifier}",
            )
        ]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape HN stories.

        Args:
            source: One of 'top', 'new', 'best', 'ask', 'show', 'job',
                    or a username to get their submissions.
            max_results: Maximum stories to fetch.
        """
        limit = max_results or self.config.max_results

        story_types = {
            "top": "topstories",
            "new": "newstories",
            "best": "beststories",
            "ask": "askstories",
            "show": "showstories",
            "job": "jobstories",
        }

        if source.lower() in story_types:
            endpoint = story_types[source.lower()]
            url = f"{HN_API}/{endpoint}.json"
            ids = await self.fetch_json(url)
            ids = ids[:limit]
        else:
            # Treat as username, get their submissions
            user_url = f"{HN_API}/user/{source}.json"
            user_data = await self.fetch_json(user_url)
            ids = (user_data or {}).get("submitted", [])[:limit]

        results = []
        for item_id in ids:
            if len(results) >= limit:
                break
            item = await self.fetch_json(f"{HN_API}/item/{item_id}.json")
            if not item:
                continue
            if item.get("type") in ("story", "job", "poll"):
                story_data = self._extract_story_data(item)
                results.append(
                    self.make_result(
                        ContentType.POST,
                        story_data,
                        url=f"https://news.ycombinator.com/item?id={item_id}",
                    )
                )

        return results

    async def scrape_comments(
        self, story_id: int, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape comments for a story.

        Args:
            story_id: HN item ID.
            max_results: Maximum comments to fetch.
        """
        limit = max_results or self.config.max_results
        item = await self.fetch_json(f"{HN_API}/item/{story_id}.json")

        if not item:
            return []

        kid_ids = item.get("kids", [])
        results = []
        await self._fetch_comments_recursive(kid_ids, results, limit, depth=0)

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Hacker News via Algolia.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        results = []
        page = 0

        while len(results) < limit:
            url = f"{ALGOLIA_API}/search"
            params = {
                "query": query,
                "tags": "story",
                "hitsPerPage": min(50, limit - len(results)),
                "page": page,
            }
            data = await self.fetch_json(url, params=params)
            hits = data.get("hits", [])

            if not hits:
                break

            for hit in hits:
                if len(results) >= limit:
                    break
                story = {
                    "story_id": hit.get("objectID", ""),
                    "title": hit.get("title", ""),
                    "url": hit.get("url", ""),
                    "author": hit.get("author", ""),
                    "points": hit.get("points", 0),
                    "num_comments": hit.get("num_comments", 0),
                    "created_at": hit.get("created_at", ""),
                    "story_text": hit.get("story_text", ""),
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                }
                results.append(
                    self.make_result(ContentType.SEARCH, story, url=story["hn_url"])
                )

            page += 1
            if page >= data.get("nbPages", 1):
                break

        return results

    async def search_by_date(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search HN sorted by date (most recent first)."""
        limit = max_results or self.config.max_results
        url = f"{ALGOLIA_API}/search_by_date"
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": min(50, limit),
        }
        data = await self.fetch_json(url, params=params)

        results = []
        for hit in data.get("hits", [])[:limit]:
            story = {
                "story_id": hit.get("objectID", ""),
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "author": hit.get("author", ""),
                "points": hit.get("points", 0),
                "num_comments": hit.get("num_comments", 0),
                "created_at": hit.get("created_at", ""),
                "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
            }
            results.append(
                self.make_result(ContentType.SEARCH, story, url=story["hn_url"])
            )

        return results

    def _extract_story_data(self, item: dict) -> dict[str, Any]:
        return {
            "story_id": item.get("id", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "author": item.get("by", ""),
            "score": item.get("score", 0),
            "num_comments": item.get("descendants", 0),
            "created_utc": item.get("time"),
            "text": item.get("text", ""),
            "type": item.get("type", "story"),
            "hn_url": f"https://news.ycombinator.com/item?id={item.get('id', '')}",
        }

    async def _fetch_comments_recursive(
        self, kid_ids: list[int], results: list[ScraperResult], limit: int, depth: int
    ):
        for kid_id in kid_ids:
            if len(results) >= limit:
                return
            item = await self.fetch_json(f"{HN_API}/item/{kid_id}.json")
            if not item or item.get("deleted") or item.get("dead"):
                continue

            comment = {
                "comment_id": item.get("id", ""),
                "author": item.get("by", "[deleted]"),
                "text": item.get("text", ""),
                "created_utc": item.get("time"),
                "depth": depth,
                "parent_id": item.get("parent"),
            }
            results.append(
                self.make_result(
                    ContentType.COMMENT,
                    comment,
                    url=f"https://news.ycombinator.com/item?id={kid_id}",
                )
            )

            child_kids = item.get("kids", [])
            if child_kids and len(results) < limit:
                await self._fetch_comments_recursive(child_kids, results, limit, depth + 1)
