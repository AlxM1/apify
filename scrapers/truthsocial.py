"""Truth Social scraper using the Mastodon-compatible API.

No API key required for public data. Truth Social is built on Mastodon and
exposes the standard Mastodon REST API at https://truthsocial.com/api/v1.
Supports: profiles, truths (posts), timelines, search, trending.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

TRUTH_SOCIAL_BASE = "https://truthsocial.com"
TRUTH_SOCIAL_API = "https://truthsocial.com/api/v1"


class TruthSocialScraper(BaseScraper):
    """Truth Social scraper using the public Mastodon-compatible API.

    No authentication required for public timelines, profiles, and search.
    Truth Social is a Mastodon fork and exposes the same REST API endpoints.

    Usage:
        scraper = TruthSocialScraper()
        results = await scraper.scrape_profile("realDonaldTrump")
        results = await scraper.scrape_posts("realDonaldTrump", max_results=50)
        results = await scraper.search("america", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "truthsocial"

    def _api_url(self, path: str) -> str:
        """Build an API endpoint URL.

        Args:
            path: API path starting with / (e.g. '/accounts/lookup').
        """
        if path.startswith("/api"):
            return f"{TRUTH_SOCIAL_BASE}{path}"
        return f"{TRUTH_SOCIAL_API}{path}"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Truth Social user profile.

        Args:
            identifier: Username, profile URL, or @handle.
        """
        username = self._parse_username(identifier)

        url = self._api_url("/accounts/lookup")
        data = await self.fetch_json(url, params={"acct": username})

        if not data or not data.get("id"):
            return []

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
            "url": data.get("url", "") or f"{TRUTH_SOCIAL_BASE}/@{username}",
            "verified": data.get("verified", False),
            "location": data.get("location", ""),
            "website": data.get("website", ""),
            "fields": [
                {
                    "name": f.get("name", ""),
                    "value": self._strip_html(f.get("value", "")),
                }
                for f in data.get("fields", [])
            ],
        }

        profile_url = profile["url"]
        return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape truths (posts) from a user's profile.

        Args:
            source: Username, @handle, or profile URL.
            max_results: Maximum truths to return.
        """
        limit = max_results or self.config.max_results
        username = self._parse_username(source)

        # Look up account ID first
        lookup_url = self._api_url("/accounts/lookup")
        account = await self.fetch_json(lookup_url, params={"acct": username})
        account_id = account.get("id")

        if not account_id:
            return []

        results: list[ScraperResult] = []
        max_id: str | None = None

        while len(results) < limit:
            statuses_url = self._api_url(f"/accounts/{account_id}/statuses")
            params: dict[str, Any] = {
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
                truth = self._extract_truth(status)
                results.append(
                    self.make_result(ContentType.POST, truth, url=truth.get("url", ""))
                )

            max_id = statuses[-1].get("id")

        return results

    async def scrape_timeline(
        self, timeline: str = "public", max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape a public timeline.

        Args:
            timeline: One of 'public', 'local', or 'trending'.
            max_results: Maximum truths to return.
        """
        limit = max_results or self.config.max_results

        if timeline == "trending":
            url = self._api_url("/trends/statuses")
        else:
            url = self._api_url("/timelines/public")

        params: dict[str, Any] = {"limit": min(40, limit)}
        if timeline == "local":
            params["local"] = "true"

        statuses = await self.fetch_json(url, params=params)

        results: list[ScraperResult] = []
        for status in statuses[:limit]:
            truth = self._extract_truth(status)
            results.append(
                self.make_result(ContentType.POST, truth, url=truth.get("url", ""))
            )

        return results

    async def scrape_trending(
        self, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape trending hashtags on Truth Social."""
        limit = max_results or self.config.max_results
        url = self._api_url("/trends/tags")
        tags = await self.fetch_json(url, params={"limit": min(20, limit)})

        results: list[ScraperResult] = []
        for tag in tags[:limit]:
            history = tag.get("history", [])
            first_day = history[0] if history else {}
            tag_data = {
                "name": tag.get("name", ""),
                "url": tag.get("url", ""),
                "uses_today": int(first_day.get("uses", 0)),
                "accounts_today": int(first_day.get("accounts", 0)),
                "total_uses_week": sum(
                    int(h.get("uses", 0)) for h in history
                ),
            }
            results.append(
                self.make_result(ContentType.TRENDING, tag_data, url=tag_data["url"])
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Truth Social for truths and accounts.

        Args:
            query: Search query string.
            max_results: Maximum results to return.
        """
        limit = max_results or self.config.max_results

        # Try v2 search endpoint first (Mastodon standard)
        url = self._api_url("/api/v2/search")
        params: dict[str, Any] = {
            "q": query,
            "type": "statuses",
            "limit": min(40, limit),
        }

        try:
            data = await self.fetch_json(url, params=params)
        except Exception:
            # Fallback to v1 search
            url = self._api_url("/search")
            data = await self.fetch_json(url, params=params)

        results: list[ScraperResult] = []

        # Status results
        for status in data.get("statuses", []):
            if len(results) >= limit:
                break
            truth = self._extract_truth(status)
            results.append(
                self.make_result(ContentType.SEARCH, truth, url=truth.get("url", ""))
            )

        # Account results
        for account in data.get("accounts", []):
            if len(results) >= limit:
                break
            profile = {
                "account_id": account.get("id", ""),
                "username": account.get("username", ""),
                "acct": account.get("acct", ""),
                "display_name": account.get("display_name", ""),
                "bio": self._strip_html(account.get("note", "")),
                "followers_count": account.get("followers_count", 0),
                "url": account.get("url", ""),
                "verified": account.get("verified", False),
            }
            results.append(
                self.make_result(ContentType.PROFILE, profile, url=profile["url"])
            )

        return results[:limit]

    # --- Extraction helpers ---

    def _extract_truth(self, status: dict) -> dict[str, Any]:
        """Extract normalized truth data from a Mastodon-format status object."""
        account = status.get("account", {})

        # Handle retruth (reblog/boost)
        reblog = status.get("reblog")
        is_retruth = reblog is not None
        content_status = reblog if is_retruth else status

        return {
            "truth_id": status.get("id", ""),
            "content": self._strip_html(content_status.get("content", "")),
            "author": account.get("acct", ""),
            "author_display_name": account.get("display_name", ""),
            "author_verified": account.get("verified", False),
            "created_at": status.get("created_at", ""),
            "url": status.get("url", ""),
            "favourites_count": content_status.get("favourites_count", 0),
            "reblogs_count": content_status.get("reblogs_count", 0),
            "replies_count": content_status.get("replies_count", 0),
            "language": content_status.get("language"),
            "visibility": status.get("visibility", "public"),
            "sensitive": content_status.get("sensitive", False),
            "spoiler_text": content_status.get("spoiler_text", ""),
            "is_retruth": is_retruth,
            "retruthed_from": (
                (reblog or {}).get("account", {}).get("acct", "")
                if is_retruth
                else None
            ),
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
            "mentions": [
                m.get("acct", "") for m in content_status.get("mentions", [])
            ],
            "card": self._extract_card(content_status.get("card")),
        }

    @staticmethod
    def _extract_card(card: dict | None) -> dict[str, str] | None:
        """Extract link preview card data if present."""
        if not card:
            return None
        return {
            "url": card.get("url", ""),
            "title": card.get("title", ""),
            "description": card.get("description", ""),
            "image": card.get("image", ""),
            "type": card.get("type", ""),
        }

    # --- Parsing helpers ---

    def _parse_username(self, identifier: str) -> str:
        """Normalize an identifier to a bare username.

        Handles profile URLs, @mentions, and plain usernames.
        """
        if identifier.startswith("http"):
            parsed = urlparse(identifier)
            path_parts = parsed.path.strip("/").split("/")
            return path_parts[-1].lstrip("@") if path_parts else ""
        return identifier.lstrip("@").strip()

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML tags, returning plain text."""
        if not text:
            return ""
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "lxml").get_text(separator=" ", strip=True)
