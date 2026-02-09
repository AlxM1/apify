"""Twitch scraper using the public GQL API and web scraping.

No API key required for the undocumented GQL endpoint.
For official Helix API: register a free app at dev.twitch.tv.
Supports: channels, streams, VODs, clips, categories, search.
"""

import json
import logging
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

# Twitch's internal GQL endpoint (no auth required for public queries)
TWITCH_GQL = "https://gql.twitch.tv/gql"
TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Public client ID used by web app


class TwitchScraper(BaseScraper):
    """Twitch scraper using the public GQL API.

    Uses Twitch's internal GraphQL endpoint (same as the web app uses).
    No API key or authentication required.

    Usage:
        scraper = TwitchScraper()
        results = await scraper.scrape_profile("shroud")
        results = await scraper.scrape_posts("shroud", max_results=20)
        results = await scraper.search("valorant", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "twitch"

    async def _gql_request(self, query: str, variables: dict | None = None) -> dict:
        """Make a GQL request to Twitch."""
        client = await self.get_client()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = await client.post(
            TWITCH_GQL,
            json=payload,
            headers={
                "Client-ID": TWITCH_CLIENT_ID,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def _gql_persisted(self, operation: str, variables: dict, sha256: str) -> dict:
        """Make a persisted GQL query."""
        client = await self.get_client()
        payload = [{
            "operationName": operation,
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256,
                }
            },
        }]
        resp = await client.post(
            TWITCH_GQL,
            json=payload,
            headers={
                "Client-ID": TWITCH_CLIENT_ID,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if isinstance(data, list) else data

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Twitch channel profile.

        Args:
            identifier: Channel name or URL.
        """
        username = self._normalize_username(identifier)

        query = """
        query {
            user(login: "%s") {
                id
                login
                displayName
                description
                profileImageURL(width: 300)
                offlineImageURL
                createdAt
                roles { isPartner isAffiliate }
                stream { id title game { name } viewersCount }
                followers { totalCount }
                lastBroadcast { startedAt title game { name } }
            }
        }
        """ % username

        data = await self._gql_request(query)
        user = data.get("data", {}).get("user")

        if not user:
            return []

        stream = user.get("stream")
        profile = {
            "user_id": user.get("id", ""),
            "username": user.get("login", username),
            "display_name": user.get("displayName", ""),
            "description": user.get("description", ""),
            "profile_image": user.get("profileImageURL", ""),
            "offline_image": user.get("offlineImageURL", ""),
            "created_at": user.get("createdAt", ""),
            "is_partner": user.get("roles", {}).get("isPartner", False),
            "is_affiliate": user.get("roles", {}).get("isAffiliate", False),
            "follower_count": user.get("followers", {}).get("totalCount", 0),
            "is_live": stream is not None,
            "current_stream": {
                "title": stream.get("title", ""),
                "game": stream.get("game", {}).get("name", ""),
                "viewers": stream.get("viewersCount", 0),
            } if stream else None,
            "last_broadcast": {
                "started_at": user.get("lastBroadcast", {}).get("startedAt", ""),
                "title": user.get("lastBroadcast", {}).get("title", ""),
                "game": (user.get("lastBroadcast") or {}).get("game", {}).get("name", "") if user.get("lastBroadcast") else "",
            } if user.get("lastBroadcast") else None,
            "url": f"https://www.twitch.tv/{username}",
        }

        return [self.make_result(ContentType.PROFILE, profile, url=profile["url"])]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape VODs and clips from a channel.

        Args:
            source: Channel name or URL.
            max_results: Maximum items to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)

        # Get VODs (past broadcasts)
        query = """
        query {
            user(login: "%s") {
                videos(first: %d, type: ARCHIVE, sort: TIME) {
                    edges {
                        node {
                            id
                            title
                            publishedAt
                            lengthSeconds
                            viewCount
                            thumbnailURLs(width: 320, height: 180)
                            game { name }
                            previewThumbnailURL(width: 320, height: 180)
                        }
                    }
                }
            }
        }
        """ % (username, min(limit, 100))

        data = await self._gql_request(query)
        edges = data.get("data", {}).get("user", {}).get("videos", {}).get("edges", [])

        results = []
        for edge in edges[:limit]:
            node = edge.get("node", {})
            vod = {
                "video_id": node.get("id", ""),
                "title": node.get("title", ""),
                "published_at": node.get("publishedAt", ""),
                "duration_seconds": node.get("lengthSeconds", 0),
                "view_count": node.get("viewCount", 0),
                "game": node.get("game", {}).get("name", "") if node.get("game") else "",
                "thumbnail": node.get("previewThumbnailURL", ""),
                "url": f"https://www.twitch.tv/videos/{node.get('id', '')}",
                "type": "vod",
            }
            results.append(
                self.make_result(ContentType.VIDEO, vod, url=vod["url"])
            )

        return results

    async def scrape_clips(
        self, channel: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape top clips from a channel.

        Args:
            channel: Channel name.
            max_results: Maximum clips.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(channel)

        query = """
        query {
            user(login: "%s") {
                clips(first: %d, criteria: { period: ALL_TIME }) {
                    edges {
                        node {
                            id
                            slug
                            title
                            viewCount
                            createdAt
                            durationSeconds
                            thumbnailURL
                            game { name }
                            curator { login displayName }
                        }
                    }
                }
            }
        }
        """ % (username, min(limit, 100))

        data = await self._gql_request(query)
        edges = data.get("data", {}).get("user", {}).get("clips", {}).get("edges", [])

        results = []
        for edge in edges[:limit]:
            node = edge.get("node", {})
            clip = {
                "clip_id": node.get("id", ""),
                "slug": node.get("slug", ""),
                "title": node.get("title", ""),
                "view_count": node.get("viewCount", 0),
                "created_at": node.get("createdAt", ""),
                "duration_seconds": node.get("durationSeconds", 0),
                "thumbnail": node.get("thumbnailURL", ""),
                "game": node.get("game", {}).get("name", "") if node.get("game") else "",
                "curator": node.get("curator", {}).get("login", "") if node.get("curator") else "",
                "url": f"https://clips.twitch.tv/{node.get('slug', '')}",
                "type": "clip",
            }
            results.append(
                self.make_result(ContentType.VIDEO, clip, url=clip["url"])
            )

        return results

    async def scrape_live_streams(
        self, game: str | None = None, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape currently live streams.

        Args:
            game: Optional game/category name to filter by.
            max_results: Maximum streams.
        """
        limit = max_results or self.config.max_results

        if game:
            query = """
            query {
                game(name: "%s") {
                    streams(first: %d) {
                        edges {
                            node {
                                id
                                title
                                viewersCount
                                broadcaster { login displayName }
                                game { name }
                                previewImageURL(width: 320, height: 180)
                            }
                        }
                    }
                }
            }
            """ % (game, min(limit, 100))
        else:
            query = """
            query {
                streams(first: %d) {
                    edges {
                        node {
                            id
                            title
                            viewersCount
                            broadcaster { login displayName }
                            game { name }
                            previewImageURL(width: 320, height: 180)
                        }
                    }
                }
            }
            """ % min(limit, 100)

        data = await self._gql_request(query)

        if game:
            edges = data.get("data", {}).get("game", {}).get("streams", {}).get("edges", [])
        else:
            edges = data.get("data", {}).get("streams", {}).get("edges", [])

        results = []
        for edge in edges[:limit]:
            node = edge.get("node", {})
            broadcaster = node.get("broadcaster", {})
            stream = {
                "stream_id": node.get("id", ""),
                "title": node.get("title", ""),
                "viewers": node.get("viewersCount", 0),
                "streamer": broadcaster.get("login", ""),
                "streamer_display": broadcaster.get("displayName", ""),
                "game": node.get("game", {}).get("name", "") if node.get("game") else "",
                "thumbnail": node.get("previewImageURL", ""),
                "url": f"https://www.twitch.tv/{broadcaster.get('login', '')}",
            }
            results.append(
                self.make_result(ContentType.STREAM, stream, url=stream["url"])
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Twitch for channels, streams, and games.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        gql_query = """
        query {
            searchFor(userQuery: "%s", options: { targets: [{index: CHANNEL}] }) {
                channels {
                    items {
                        id
                        login
                        displayName
                        description
                        profileImageURL(width: 300)
                        followers { totalCount }
                        stream { title viewersCount game { name } }
                    }
                }
            }
        }
        """ % query.replace('"', '\\"')

        data = await self._gql_request(gql_query)
        items = data.get("data", {}).get("searchFor", {}).get("channels", {}).get("items", [])

        results = []
        for item in items[:limit]:
            stream = item.get("stream")
            channel = {
                "user_id": item.get("id", ""),
                "username": item.get("login", ""),
                "display_name": item.get("displayName", ""),
                "description": item.get("description", ""),
                "profile_image": item.get("profileImageURL", ""),
                "follower_count": item.get("followers", {}).get("totalCount", 0),
                "is_live": stream is not None,
                "stream_title": stream.get("title", "") if stream else "",
                "stream_viewers": stream.get("viewersCount", 0) if stream else 0,
                "stream_game": stream.get("game", {}).get("name", "") if stream and stream.get("game") else "",
                "url": f"https://www.twitch.tv/{item.get('login', '')}",
            }
            results.append(
                self.make_result(ContentType.SEARCH, channel, url=channel["url"])
            )

        return results

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier.lstrip("@").lower()
