"""SoundCloud scraper using web scraping with stealth headers.

No API key required. Extracts data from embedded JSON hydration data
(window.__sc_hydration) and resolves the client_id from page scripts for
API access. Supports: artist profiles, tracks, playlists, search.
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

SOUNDCLOUD_BASE = "https://soundcloud.com"
SOUNDCLOUD_API_V2 = "https://api-v2.soundcloud.com"


class SoundCloudScraper(BaseScraper):
    """SoundCloud scraper using stealth web scraping and extracted client_id.

    No authentication needed. Extracts the client_id from SoundCloud's
    JavaScript bundles to access the internal API. Falls back to parsing
    hydration data and HTML when the API is unavailable.

    Usage:
        scraper = SoundCloudScraper()
        results = await scraper.scrape_profile("flaboradio")
        results = await scraper.scrape_posts("flaboradio", max_results=50)
        results = await scraper.search("lo-fi beats", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()
        self._client_id: str | None = None
        self._stealth_client = None

    @property
    def platform_name(self) -> str:
        return "soundcloud"

    async def get_client(self):
        """Override to use stealth headers."""
        if self._stealth_client is None or self._stealth_client.is_closed:
            self._stealth_client = self._stealth.create_client(
                proxy=self.config.proxy,
                timeout=self.config.timeout,
            )
        return self._stealth_client

    async def _extract_client_id(self) -> str | None:
        """Extract the client_id from SoundCloud's JavaScript bundles.

        SoundCloud embeds a client_id in its JS assets which is required
        for API v2 calls. This method fetches the main page and parses
        the script bundles to find it.
        """
        if self._client_id:
            return self._client_id

        try:
            resp = await self.fetch(SOUNDCLOUD_BASE)
            soup = BeautifulSoup(resp.text, "lxml")

            # Find cross-origin script tags (the JS bundles)
            script_urls = []
            for script in soup.find_all("script", src=True):
                src = script["src"]
                if "sndcdn.com" in src or src.endswith(".js"):
                    script_urls.append(src)

            # Check the last few scripts (client_id is usually in the later bundles)
            for script_url in reversed(script_urls[-5:]):
                try:
                    js_resp = await self.fetch(script_url)
                    # Look for client_id pattern
                    match = re.search(r'client_id\s*[:=]\s*["\']([a-zA-Z0-9]{32})["\']', js_resp.text)
                    if match:
                        self._client_id = match.group(1)
                        logger.info(f"Extracted SoundCloud client_id: {self._client_id[:8]}...")
                        return self._client_id
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Failed to extract client_id: {e}")

        return None

    async def _api_get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make an API v2 request with the extracted client_id."""
        client_id = await self._extract_client_id()
        if not client_id:
            return None

        full_params = {"client_id": client_id}
        if params:
            full_params.update(params)

        url = f"{SOUNDCLOUD_API_V2}/{endpoint}"
        try:
            return await self.fetch_json(url, params=full_params)
        except Exception as e:
            logger.warning(f"SoundCloud API request failed ({endpoint}): {e}")
            return None

    async def _resolve_url(self, sc_url: str) -> dict | None:
        """Resolve a SoundCloud URL to its API resource."""
        return await self._api_get("resolve", {"url": sc_url})

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a SoundCloud artist/user profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        profile_url = f"{SOUNDCLOUD_BASE}/{username}"

        # Strategy 1: Try API v2 resolve
        api_data = await self._resolve_url(profile_url)
        if api_data and api_data.get("kind") == "user":
            profile = self._normalize_user(api_data)
            return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

        # Strategy 2: Parse hydration data from the page
        resp = await self.fetch(profile_url)
        hydration = self._extract_hydration(resp.text)

        if hydration:
            user_data = self._find_in_hydration(hydration, "user")
            if user_data:
                profile = self._normalize_user(user_data)
                return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

        # Strategy 3: Fall back to HTML meta tags
        soup = BeautifulSoup(resp.text, "lxml")
        profile = {
            "username": username,
            "display_name": self._meta(soup, "og:title") or username,
            "description": self._meta(soup, "og:description") or "",
            "avatar_url": self._meta(soup, "og:image") or "",
            "profile_url": profile_url,
        }

        return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape tracks from a SoundCloud user.

        Args:
            source: Username or profile URL.
            max_results: Maximum tracks to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        profile_url = f"{SOUNDCLOUD_BASE}/{username}"

        # Strategy 1: Try API v2
        resolved = await self._resolve_url(profile_url)
        if resolved and resolved.get("id"):
            user_id = resolved["id"]
            return await self._fetch_tracks_api(user_id, limit)

        # Strategy 2: Parse hydration data
        resp = await self.fetch(profile_url + "/tracks")
        hydration = self._extract_hydration(resp.text)

        if hydration:
            tracks = self._find_tracks_in_hydration(hydration, limit)
            if tracks:
                return tracks

        # Strategy 3: HTML fallback
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_tracks_from_html(soup, username, limit)

    async def scrape_track(self, track_url: str) -> list[ScraperResult]:
        """Scrape metadata for a single track.

        Args:
            track_url: Full URL to the track page.
        """
        # Strategy 1: API resolve
        api_data = await self._resolve_url(track_url)
        if api_data and api_data.get("kind") == "track":
            track = self._normalize_track(api_data)
            return [self.make_result(ContentType.POST, track, url=track_url)]

        # Strategy 2: Hydration data
        resp = await self.fetch(track_url)
        hydration = self._extract_hydration(resp.text)

        if hydration:
            for item in hydration:
                if isinstance(item, dict) and item.get("hydratable") == "sound":
                    track_data = item.get("data", {})
                    track = self._normalize_track(track_data)
                    return [self.make_result(ContentType.POST, track, url=track_url)]

        # Strategy 3: HTML fallback
        soup = BeautifulSoup(resp.text, "lxml")
        track = {
            "title": self._meta(soup, "og:title") or "",
            "description": self._meta(soup, "og:description") or "",
            "artwork_url": self._meta(soup, "og:image") or "",
            "url": track_url,
        }
        return [self.make_result(ContentType.POST, track, url=track_url)]

    async def scrape_playlist(
        self, playlist_url: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape tracks from a SoundCloud playlist/set.

        Args:
            playlist_url: Full URL to the playlist page.
            max_results: Maximum tracks to fetch.
        """
        limit = max_results or self.config.max_results

        # Strategy 1: API resolve
        api_data = await self._resolve_url(playlist_url)
        if api_data and api_data.get("kind") == "playlist":
            return self._extract_playlist_tracks(api_data, limit, playlist_url)

        # Strategy 2: Hydration data
        resp = await self.fetch(playlist_url)
        hydration = self._extract_hydration(resp.text)

        if hydration:
            for item in hydration:
                if isinstance(item, dict) and item.get("hydratable") == "playlist":
                    playlist_data = item.get("data", {})
                    return self._extract_playlist_tracks(playlist_data, limit, playlist_url)

        return []

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search SoundCloud for tracks.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Strategy 1: Try API v2 search
        results = await self._search_api(query, limit)
        if results:
            return results

        # Strategy 2: Scrape the search results page
        return await self._search_html(query, limit)

    async def search_users(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search SoundCloud for users/artists.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        data = await self._api_get("search/users", {"q": query, "limit": min(limit, 50)})
        if not data:
            return []

        results = []
        for item in data.get("collection", []):
            if len(results) >= limit:
                break
            if item.get("kind") == "user":
                profile = self._normalize_user(item)
                results.append(
                    self.make_result(
                        ContentType.SEARCH, profile, url=profile.get("profile_url", "")
                    )
                )

        return results

    # --- API-based fetching ---

    async def _fetch_tracks_api(self, user_id: int, limit: int) -> list[ScraperResult]:
        """Fetch tracks for a user via API v2."""
        results = []
        offset = 0
        batch_size = min(limit, 50)

        while len(results) < limit:
            data = await self._api_get(
                f"users/{user_id}/tracks",
                {"limit": batch_size, "offset": offset},
            )
            if not data:
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for item in collection:
                if len(results) >= limit:
                    break
                track = self._normalize_track(item)
                results.append(
                    self.make_result(ContentType.POST, track, url=track.get("url", ""))
                )

            next_href = data.get("next_href")
            if not next_href:
                break

            offset += batch_size

        return results

    async def _search_api(self, query: str, limit: int) -> list[ScraperResult]:
        """Search tracks via API v2."""
        results = []
        offset = 0
        batch_size = min(limit, 50)

        while len(results) < limit:
            data = await self._api_get(
                "search/tracks",
                {"q": query, "limit": batch_size, "offset": offset},
            )
            if not data:
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for item in collection:
                if len(results) >= limit:
                    break
                track = self._normalize_track(item)
                results.append(
                    self.make_result(ContentType.SEARCH, track, url=track.get("url", ""))
                )

            next_href = data.get("next_href")
            if not next_href:
                break

            offset += batch_size

        return results

    # --- HTML scraping ---

    async def _search_html(self, query: str, limit: int) -> list[ScraperResult]:
        """Search SoundCloud by scraping the search results page."""
        search_url = f"{SOUNDCLOUD_BASE}/search?q={quote(query)}"
        resp = await self.fetch(search_url)

        hydration = self._extract_hydration(resp.text)
        if hydration:
            results = []
            for item in hydration:
                if len(results) >= limit:
                    break
                if isinstance(item, dict) and item.get("hydratable") == "search":
                    search_data = item.get("data", {})
                    for entry in search_data.get("collection", []):
                        if len(results) >= limit:
                            break
                        if entry.get("kind") == "track":
                            track = self._normalize_track(entry)
                            results.append(
                                self.make_result(
                                    ContentType.SEARCH, track, url=track.get("url", "")
                                )
                            )
                        elif entry.get("kind") == "user":
                            user = self._normalize_user(entry)
                            results.append(
                                self.make_result(
                                    ContentType.SEARCH, user, url=user.get("profile_url", "")
                                )
                            )
            if results:
                return results

        # Fallback: parse links
        soup = BeautifulSoup(resp.text, "lxml")
        return self._extract_tracks_from_html(soup, "", limit, content_type=ContentType.SEARCH)

    def _extract_tracks_from_html(
        self,
        soup: BeautifulSoup,
        username: str,
        limit: int,
        content_type: ContentType = ContentType.POST,
    ) -> list[ScraperResult]:
        """Extract track data from HTML page."""
        results = []

        # Look for sound items in the page
        for item in soup.find_all("article"):
            if len(results) >= limit:
                break

            title_el = item.find("a", class_=re.compile(r"soundTitle__title"))
            if not title_el:
                title_el = item.find("a", {"itemprop": "url"})

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"{SOUNDCLOUD_BASE}{href}"

            track = {
                "title": title,
                "url": href,
                "author": username,
            }
            results.append(self.make_result(content_type, track, url=href))

        return results

    # --- Hydration data parsing ---

    def _extract_hydration(self, html: str) -> list[dict] | None:
        """Extract the __sc_hydration JSON data from a SoundCloud page.

        SoundCloud embeds structured data in a script tag as:
        window.__sc_hydration = [...];
        """
        match = re.search(
            r'window\.__sc_hydration\s*=\s*(\[.+?\])\s*;',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.debug("Failed to parse __sc_hydration JSON")

        # Alternative pattern: __sc_version or similar
        match = re.search(
            r'<script>\s*window\.__sc_hydration\s*=\s*(\[.+?\])',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _find_in_hydration(self, hydration: list[dict], hydratable: str) -> dict | None:
        """Find a specific hydratable item in the hydration data."""
        for item in hydration:
            if isinstance(item, dict) and item.get("hydratable") == hydratable:
                return item.get("data", {})
        return None

    def _find_tracks_in_hydration(
        self, hydration: list[dict], limit: int
    ) -> list[ScraperResult]:
        """Extract tracks from hydration data."""
        results = []

        for item in hydration:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue

            # Look for sound collections
            data = item.get("data", {})
            if isinstance(data, dict):
                collection = data.get("collection") or data.get("tracks")
                if isinstance(collection, list):
                    for entry in collection:
                        if len(results) >= limit:
                            break
                        if isinstance(entry, dict) and entry.get("kind") == "track":
                            track = self._normalize_track(entry)
                            results.append(
                                self.make_result(
                                    ContentType.POST, track, url=track.get("url", "")
                                )
                            )

            # Individual sound items
            if item.get("hydratable") == "sound" and isinstance(data, dict):
                track = self._normalize_track(data)
                results.append(
                    self.make_result(ContentType.POST, track, url=track.get("url", ""))
                )

        return results

    # --- Data normalization ---

    def _normalize_user(self, data: dict) -> dict:
        """Normalize a user/artist data dict."""
        return {
            "user_id": data.get("id", ""),
            "username": data.get("permalink", "") or data.get("username", ""),
            "display_name": data.get("username", "") or data.get("full_name", ""),
            "description": data.get("description", ""),
            "avatar_url": data.get("avatar_url", ""),
            "city": data.get("city", ""),
            "country": data.get("country_code", ""),
            "follower_count": data.get("followers_count", 0),
            "following_count": data.get("followings_count", 0),
            "track_count": data.get("track_count", 0),
            "playlist_count": data.get("playlist_count", 0),
            "likes_count": data.get("likes_count", 0),
            "verified": data.get("verified", False),
            "profile_url": data.get("permalink_url", ""),
            "created_at": data.get("created_at", ""),
            "last_modified": data.get("last_modified", ""),
        }

    def _normalize_track(self, data: dict) -> dict:
        """Normalize a track data dict."""
        user = data.get("user", {})
        publisher = data.get("publisher_metadata", {}) or {}

        return {
            "track_id": data.get("id", ""),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "artist": user.get("username", ""),
            "artist_id": user.get("id", ""),
            "artist_permalink": user.get("permalink", ""),
            "duration_ms": data.get("duration", 0),
            "duration_formatted": self._format_duration(data.get("duration", 0)),
            "genre": data.get("genre", ""),
            "tag_list": data.get("tag_list", ""),
            "playback_count": data.get("playback_count", 0),
            "like_count": data.get("likes_count", 0) or data.get("favoritings_count", 0),
            "repost_count": data.get("reposts_count", 0),
            "comment_count": data.get("comment_count", 0),
            "download_count": data.get("download_count", 0),
            "artwork_url": data.get("artwork_url", ""),
            "waveform_url": data.get("waveform_url", ""),
            "url": data.get("permalink_url", ""),
            "created_at": data.get("created_at", ""),
            "release_date": publisher.get("release_title", ""),
            "license": data.get("license", ""),
            "downloadable": data.get("downloadable", False),
            "streamable": data.get("streamable", True),
            "is_public": data.get("sharing", "") == "public",
        }

    def _extract_playlist_tracks(
        self, playlist_data: dict, limit: int, playlist_url: str
    ) -> list[ScraperResult]:
        """Extract tracks from a playlist data dict."""
        results = []

        # Add playlist metadata as a result
        playlist_info = {
            "playlist_id": playlist_data.get("id", ""),
            "title": playlist_data.get("title", ""),
            "description": playlist_data.get("description", ""),
            "track_count": playlist_data.get("track_count", 0),
            "duration_ms": playlist_data.get("duration", 0),
            "like_count": playlist_data.get("likes_count", 0),
            "repost_count": playlist_data.get("reposts_count", 0),
            "artwork_url": playlist_data.get("artwork_url", ""),
            "url": playlist_data.get("permalink_url", playlist_url),
            "created_at": playlist_data.get("created_at", ""),
            "is_album": playlist_data.get("is_album", False),
        }
        results.append(
            self.make_result(ContentType.PLAYLIST, playlist_info, url=playlist_url)
        )

        # Add individual tracks
        tracks = playlist_data.get("tracks", [])
        for track_data in tracks:
            if len(results) >= limit:
                break
            if isinstance(track_data, dict) and track_data.get("title"):
                track = self._normalize_track(track_data)
                results.append(
                    self.make_result(ContentType.POST, track, url=track.get("url", ""))
                )

        return results

    # --- Utilities ---

    def _normalize_username(self, identifier: str) -> str:
        """Extract a username from various input formats."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            parts = path.split("/")
            return parts[0] if parts else identifier
        return identifier.strip("@/")

    @staticmethod
    def _format_duration(ms: int) -> str:
        """Format milliseconds into a human-readable duration string."""
        if not ms:
            return "0:00"
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

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
