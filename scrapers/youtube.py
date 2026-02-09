"""YouTube scraper using yt-dlp for metadata extraction.

No API key required. Uses yt-dlp's --dump-json for metadata without downloading videos.
Supports: video metadata, channel profiles, playlists, search, comments.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)


class YouTubeScraper(BaseScraper):
    """YouTube scraper powered by yt-dlp.

    Usage:
        scraper = YouTubeScraper()
        # Scrape a channel
        results = await scraper.scrape_profile("@MrBeast")
        # Scrape video metadata from a channel/playlist
        results = await scraper.scrape_posts("https://youtube.com/@MrBeast", max_results=50)
        # Search YouTube
        results = await scraper.search("python tutorial", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "youtube"

    def _run_ytdlp(self, url: str, extra_args: list[str] | None = None) -> list[dict]:
        """Run yt-dlp and return parsed JSON output."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--ignore-errors",
            "--flat-playlist",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(url)

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout * 10,
            )
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timed out")
            return []

        results = []
        for line in proc.stdout.strip().split("\n"):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return results

    def _run_ytdlp_full(self, url: str, extra_args: list[str] | None = None) -> list[dict]:
        """Run yt-dlp with full metadata (not flat-playlist)."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--ignore-errors",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(url)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout * 10,
            )
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timed out")
            return []

        results = []
        for line in proc.stdout.strip().split("\n"):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return results

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a YouTube channel profile.

        Args:
            identifier: Channel URL, handle (@username), or channel ID.
        """
        url = self._normalize_channel_url(identifier)

        # Get channel info via the /about or /videos page
        raw_items = await asyncio.to_thread(
            self._run_ytdlp,
            f"{url}/videos",
            ["--playlist-end", "1"],
        )

        if not raw_items:
            logger.warning(f"No data found for channel: {identifier}")
            return []

        # Extract channel-level metadata from the first video
        first = raw_items[0]
        channel_data = {
            "channel_id": first.get("channel_id", ""),
            "channel_name": first.get("channel", "") or first.get("uploader", ""),
            "channel_url": first.get("channel_url", "") or first.get("uploader_url", ""),
            "description": first.get("description", ""),
            "subscriber_count": first.get("channel_follower_count"),
            "channel_handle": first.get("uploader_id", ""),
        }

        return [self.make_result(ContentType.PROFILE, channel_data, url=url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape video metadata from a channel, playlist, or single video.

        Args:
            source: YouTube URL (channel, playlist, or video).
            max_results: Maximum number of videos to fetch.
        """
        limit = max_results or self.config.max_results

        # Use flat-playlist for listing, then get details for each
        extra = ["--playlist-end", str(limit)]

        raw_items = await asyncio.to_thread(self._run_ytdlp, source, extra)

        results = []
        for item in raw_items[:limit]:
            video_data = self._extract_video_data(item)
            results.append(
                self.make_result(
                    ContentType.VIDEO,
                    video_data,
                    url=item.get("url", item.get("webpage_url", "")),
                )
            )

        return results

    async def scrape_video_full(self, video_url: str) -> list[ScraperResult]:
        """Scrape full metadata for a single video (including comments if available)."""
        raw_items = await asyncio.to_thread(
            self._run_ytdlp_full,
            video_url,
            ["--write-comments", "--extractor-args", "youtube:max_comments=100"],
        )

        results = []
        for item in raw_items:
            video_data = self._extract_video_data(item)
            # Include comments if available
            comments = item.get("comments", [])
            if comments:
                video_data["comments"] = [
                    {
                        "author": c.get("author", ""),
                        "text": c.get("text", ""),
                        "likes": c.get("like_count", 0),
                        "timestamp": c.get("timestamp"),
                        "is_reply": c.get("parent", "root") != "root",
                    }
                    for c in comments[:100]
                ]
            results.append(
                self.make_result(ContentType.VIDEO, video_data, url=video_url)
            )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search YouTube.

        Args:
            query: Search query string.
            max_results: Maximum results (default 20).
        """
        limit = max_results or min(self.config.max_results, 50)
        search_url = f"ytsearch{limit}:{query}"

        raw_items = await asyncio.to_thread(self._run_ytdlp, search_url)

        results = []
        for item in raw_items[:limit]:
            video_data = self._extract_video_data(item)
            results.append(
                self.make_result(
                    ContentType.SEARCH,
                    video_data,
                    url=item.get("url", item.get("webpage_url", "")),
                )
            )

        return results

    def _normalize_channel_url(self, identifier: str) -> str:
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if identifier.startswith("@"):
            return f"https://www.youtube.com/{identifier}"
        if identifier.startswith("UC"):
            return f"https://www.youtube.com/channel/{identifier}"
        return f"https://www.youtube.com/@{identifier}"

    def _extract_video_data(self, item: dict) -> dict[str, Any]:
        return {
            "video_id": item.get("id", ""),
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "channel_name": item.get("channel", "") or item.get("uploader", ""),
            "channel_id": item.get("channel_id", ""),
            "channel_url": item.get("channel_url", ""),
            "upload_date": item.get("upload_date", ""),
            "duration": item.get("duration"),
            "view_count": item.get("view_count"),
            "like_count": item.get("like_count"),
            "comment_count": item.get("comment_count"),
            "thumbnail": item.get("thumbnail", ""),
            "tags": item.get("tags", []),
            "categories": item.get("categories", []),
            "is_live": item.get("is_live", False),
            "was_live": item.get("was_live", False),
            "webpage_url": item.get("webpage_url", item.get("url", "")),
        }
