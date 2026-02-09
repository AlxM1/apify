"""Mastodon scraper using the open Mastodon API.

No API key required for public data. Mastodon instances expose a standard REST API.
Supports: profiles, toots/posts, timelines, search, trending.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

DEFAULT_INSTANCE = "https://mastodon.social"


class MastodonScraper(BaseScraper):
    """Mastodon scraper using the public API.

    No authentication required for public timelines, profiles, and search.
    Works with any Mastodon-compatible instance (Mastodon, Pleroma, Akkoma, etc.)

    Usage:
        scraper = MastodonScraper()
        results = await scraper.scrape_profile("Gargron@mastodon.social")
        results = await scraper.scrape_posts("Gargron@mastodon.social", max_results=50)
        results = await scraper.search("python", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None, instance: str | None = None):
        super().__init__(config)
        self.instance = (instance or DEFAULT_INSTANCE).rstrip("/")

    @property
    def platform_name(self) -> str:
        return "mastodon"

    def _api_url(self, path: str, instance: str | None = None) -> str:
        base = (instance or self.instance).rstrip("/")
        return f"{base}/api/v1{path}" if not path.startswith("/api") else f"{base}{path}"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Mastodon profile.

        Args:
            identifier: Full handle (user@instance.social), username, or profile URL.
        """
        instance, username = self._parse_identifier(identifier)

        # Look up the account
        url = self._api_url("/accounts/lookup", instance)
        data = await self.fetch_json(url, params={"acct": username})

        profile = {
            "account_id": data.get("id", ""),
            "username": data.get("username", ""),
            "acct": data.get("acct", ""),
            "display_name": data.get("display_name", ""),
            "bio": self._strip_html(data.get("note", "")),
            "avatar": data.get("avatar", ""),
            "header": data.get("header", ""),
            "followers_count": data.get("followers_count", 0),
            "following_count": data.get("following_count", 0),
            "statuses_count": data.get("statuses_count", 0),
            "created_at": data.get("created_at", ""),
            "bot": data.get("bot", False),
            "locked": data.get("locked", False),
            "url": data.get("url", ""),
            "fields": [
                {"name": f.get("name", ""), "value": self._strip_html(f.get("value", ""))}
                for f in data.get("fields", [])
            ],
        }

        return [self.make_result(ContentType.PROFILE, profile, url=profile["url"])]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape toots from a user's profile.

        Args:
            source: Full handle, username, or profile URL.
            max_results: Maximum toots.
        """
        limit = max_results or self.config.max_results
        instance, username = self._parse_identifier(source)

        # Look up account ID
        lookup_url = self._api_url("/accounts/lookup", instance)
        account = await self.fetch_json(lookup_url, params={"acct": username})
        account_id = account.get("id")

        if not account_id:
            return []

        # Fetch statuses
        results = []
        max_id = None

        while len(results) < limit:
            statuses_url = self._api_url(f"/accounts/{account_id}/statuses", instance)
            params = {
                "limit": min(40, limit - len(results)),
                "exclude_replies": "false",
            }
            if max_id:
                params["max_id"] = max_id

            statuses = await self.fetch_json(statuses_url, params=params)

            if not statuses:
                break

            for status in statuses:
                if len(results) >= limit:
                    break
                toot = self._extract_toot(status)
                results.append(
                    self.make_result(ContentType.POST, toot, url=toot.get("url", ""))
                )

            max_id = statuses[-1].get("id")

        return results

    async def scrape_timeline(
        self, timeline: str = "public", max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape a public timeline.

        Args:
            timeline: 'public', 'local', or 'trending'.
            max_results: Maximum toots.
        """
        limit = max_results or self.config.max_results

        if timeline == "trending":
            url = self._api_url("/trends/statuses")
        elif timeline == "local":
            url = self._api_url("/timelines/public")
        else:
            url = self._api_url("/timelines/public")

        params = {"limit": min(40, limit)}
        if timeline == "local":
            params["local"] = "true"

        statuses = await self.fetch_json(url, params=params)

        results = []
        for status in statuses[:limit]:
            toot = self._extract_toot(status)
            results.append(
                self.make_result(ContentType.POST, toot, url=toot.get("url", ""))
            )

        return results

    async def scrape_trending(self, max_results: int | None = None) -> list[ScraperResult]:
        """Scrape trending hashtags."""
        limit = max_results or self.config.max_results
        url = self._api_url("/trends/tags")
        tags = await self.fetch_json(url, params={"limit": min(20, limit)})

        results = []
        for tag in tags[:limit]:
            tag_data = {
                "name": tag.get("name", ""),
                "url": tag.get("url", ""),
                "uses_today": int(tag.get("history", [{}])[0].get("uses", 0)) if tag.get("history") else 0,
                "accounts_today": int(tag.get("history", [{}])[0].get("accounts", 0)) if tag.get("history") else 0,
                "total_uses_week": sum(int(h.get("uses", 0)) for h in tag.get("history", [])),
            }
            results.append(
                self.make_result(ContentType.TRENDING, tag_data, url=tag_data["url"])
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Mastodon.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # v2 search endpoint (public, no auth needed for basic search)
        url = self._api_url("/api/v2/search")
        params = {
            "q": query,
            "type": "statuses",
            "limit": min(40, limit),
        }

        try:
            data = await self.fetch_json(url, params=params)
        except Exception:
            # Fallback to v1
            url = self._api_url("/search")
            data = await self.fetch_json(url, params=params)

        results = []
        for status in data.get("statuses", [])[:limit]:
            toot = self._extract_toot(status)
            results.append(
                self.make_result(ContentType.SEARCH, toot, url=toot.get("url", ""))
            )

        # Also include account results
        for account in data.get("accounts", []):
            if len(results) >= limit:
                break
            profile = {
                "username": account.get("username", ""),
                "acct": account.get("acct", ""),
                "display_name": account.get("display_name", ""),
                "bio": self._strip_html(account.get("note", "")),
                "followers_count": account.get("followers_count", 0),
                "url": account.get("url", ""),
            }
            results.append(
                self.make_result(ContentType.PROFILE, profile, url=profile["url"])
            )

        return results[:limit]

    def _extract_toot(self, status: dict) -> dict[str, Any]:
        account = status.get("account", {})

        # Handle reblog (boost)
        reblog = status.get("reblog")
        is_reblog = reblog is not None
        content_status = reblog if is_reblog else status

        return {
            "toot_id": status.get("id", ""),
            "content": self._strip_html(content_status.get("content", "")),
            "author": account.get("acct", ""),
            "author_display_name": account.get("display_name", ""),
            "created_at": status.get("created_at", ""),
            "url": status.get("url", ""),
            "favourites_count": content_status.get("favourites_count", 0),
            "reblogs_count": content_status.get("reblogs_count", 0),
            "replies_count": content_status.get("replies_count", 0),
            "language": content_status.get("language"),
            "visibility": status.get("visibility", "public"),
            "sensitive": content_status.get("sensitive", False),
            "spoiler_text": content_status.get("spoiler_text", ""),
            "is_reblog": is_reblog,
            "reblogged_from": (reblog or {}).get("account", {}).get("acct", "") if is_reblog else None,
            "media": [
                {
                    "type": m.get("type", ""),
                    "url": m.get("url", ""),
                    "preview_url": m.get("preview_url", ""),
                    "description": m.get("description", ""),
                }
                for m in content_status.get("media_attachments", [])
            ],
            "tags": [t.get("name", "") for t in content_status.get("tags", [])],
            "mentions": [m.get("acct", "") for m in content_status.get("mentions", [])],
        }

    def _parse_identifier(self, identifier: str) -> tuple[str, str]:
        """Parse an identifier into (instance_url, username)."""
        if identifier.startswith("http"):
            parsed = urlparse(identifier)
            instance = f"{parsed.scheme}://{parsed.netloc}"
            path_parts = parsed.path.strip("/").split("/")
            username = path_parts[-1].lstrip("@") if path_parts else ""
            return instance, username

        if "@" in identifier:
            parts = identifier.lstrip("@").split("@")
            if len(parts) == 2:
                return f"https://{parts[1]}", parts[0]
            return self.instance, parts[0]

        return self.instance, identifier

    @staticmethod
    def _strip_html(text: str) -> str:
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "lxml").get_text(separator=" ", strip=True)
