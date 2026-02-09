"""Base scraper class that all platform scrapers inherit from."""

import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    POST = "post"
    PROFILE = "profile"
    COMMENT = "comment"
    VIDEO = "video"
    IMAGE = "image"
    STORY = "story"
    REEL = "reel"
    ARTICLE = "article"
    CHANNEL = "channel"
    SEARCH = "search"
    TRENDING = "trending"
    HASHTAG = "hashtag"
    PLAYLIST = "playlist"
    STREAM = "stream"
    MESSAGE = "message"


@dataclass
class ScraperConfig:
    """Configuration for a scraper run."""
    max_results: int = 100
    proxy: str | None = None
    proxy_list: list[str] = field(default_factory=list)
    timeout: int = 30
    delay_between_requests: float = 1.0
    output_format: str = "json"  # json, csv, jsonl
    output_dir: str = "output"
    headless: bool = True
    cookies_file: str | None = None
    custom_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ScraperResult:
    """Standardized result from any scraper."""
    platform: str
    content_type: str
    data: dict[str, Any]
    url: str = ""
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw_data: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        result = asdict(self)
        if result["raw_data"] is None:
            del result["raw_data"]
        return result


class BaseScraper(ABC):
    """Abstract base class for all platform scrapers.

    Every scraper must implement:
      - platform_name: property returning the platform identifier
      - scrape_profile(url_or_username): scrape a user profile
      - scrape_posts(url_or_query, max_results): scrape posts/content
      - search(query, max_results): search the platform
    """

    def __init__(self, config: ScraperConfig | None = None):
        self.config = config or ScraperConfig()
        self._client: httpx.AsyncClient | None = None
        self._results: list[ScraperResult] = []
        self._request_count = 0

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g. 'youtube', 'reddit')."""
        ...

    @abstractmethod
    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a user/channel profile."""
        ...

    @abstractmethod
    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts/content from a URL, username, hashtag, etc."""
        ...

    @abstractmethod
    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search the platform."""
        ...

    # --- HTTP helpers ---

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                **self.config.custom_headers,
            }
            proxy = self.config.proxy
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=self.config.timeout,
                proxy=proxy,
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, url: str, **kwargs) -> httpx.Response:
        """Fetch a URL with rate limiting and retry logic."""
        client = await self.get_client()
        self._throttle()
        for attempt in range(3):
            try:
                resp = await client.get(url, **kwargs)
                resp.raise_for_status()
                self._request_count += 1
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                if attempt == 2:
                    raise
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"[{self.platform_name}] Request failed ({e}), "
                    f"retrying in {wait}s..."
                )
                time.sleep(wait)
        raise RuntimeError("Unreachable")

    async def fetch_json(self, url: str, **kwargs) -> dict:
        resp = await self.fetch(url, **kwargs)
        return resp.json()

    def _throttle(self):
        if self.config.delay_between_requests > 0 and self._request_count > 0:
            time.sleep(self.config.delay_between_requests)

    # --- Result helpers ---

    def make_result(
        self,
        content_type: ContentType | str,
        data: dict[str, Any],
        url: str = "",
    ) -> ScraperResult:
        ct = content_type.value if isinstance(content_type, ContentType) else content_type
        result = ScraperResult(
            platform=self.platform_name,
            content_type=ct,
            data=data,
            url=url,
        )
        self._results.append(result)
        return result

    # --- Export ---

    def export(self, results: list[ScraperResult] | None = None) -> str:
        """Export results to the configured format. Returns the file path."""
        items = results or self._results
        if not items:
            logger.warning("No results to export.")
            return ""

        out_dir = Path(self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{self.platform_name}_{ts}"

        if self.config.output_format == "jsonl":
            path = out_dir / f"{base}.jsonl"
            with open(path, "w") as f:
                for item in items:
                    f.write(json.dumps(item.to_dict()) + "\n")
        elif self.config.output_format == "csv":
            import pandas as pd
            path = out_dir / f"{base}.csv"
            rows = [item.to_dict() for item in items]
            df = pd.json_normalize(rows)
            df.to_csv(path, index=False)
        else:
            path = out_dir / f"{base}.json"
            with open(path, "w") as f:
                json.dump([item.to_dict() for item in items], f, indent=2)

        logger.info(f"Exported {len(items)} results to {path}")
        return str(path)

    # --- Lifecycle ---

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
