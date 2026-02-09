"""Twitter/X scraper using Playwright browser automation with stealth.

No API key required. Uses browser automation to scrape public tweets.
Supports: tweets, profiles, search, trending.
"""

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

TWITTER_BASE = "https://x.com"


class TwitterScraper(BaseScraper):
    """Twitter/X scraper using Playwright browser automation.

    Scrapes public tweets without API keys by rendering pages with a headless browser.

    Usage:
        scraper = TwitterScraper()
        results = await scraper.scrape_profile("elonmusk")
        results = await scraper.scrape_posts("elonmusk", max_results=50)
        results = await scraper.search("python programming", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._browser = None
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "twitter"

    async def _get_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            stealth_cfg = await self._stealth.playwright_stealth_config()
            self._browser = await self._pw.chromium.launch(
                headless=self.config.headless,
                args=stealth_cfg["launch_args"]["args"],
            )
        return self._browser

    async def _new_page(self):
        browser = await self._get_browser()
        stealth_cfg = await self._stealth.playwright_stealth_config()
        context = await browser.new_context(**stealth_cfg["context_args"])
        page = await context.new_page()
        # Inject stealth scripts
        for script in stealth_cfg["stealth_scripts"]:
            await page.add_init_script(script)
        return page

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Twitter/X user profile.

        Args:
            identifier: Username (with or without @) or profile URL.
        """
        username = self._normalize_username(identifier)
        page = await self._new_page()

        try:
            url = f"{TWITTER_BASE}/{username}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            content = await page.content()
            soup = BeautifulSoup(content, "lxml")

            # Intercept API responses for structured data
            profile = {
                "username": username,
                "name": self._meta(soup, "og:title") or username,
                "description": self._meta(soup, "og:description") or "",
                "image": self._meta(soup, "og:image") or "",
                "url": url,
            }

            # Try to extract follower counts from page text
            text = soup.get_text()
            followers_match = re.search(r"([\d,.]+[KMB]?)\s*Followers", text)
            following_match = re.search(r"([\d,.]+[KMB]?)\s*Following", text)
            if followers_match:
                profile["followers_count"] = self._parse_count(followers_match.group(1))
            if following_match:
                profile["following_count"] = self._parse_count(following_match.group(1))

            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await page.context.close()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape tweets from a user's timeline.

        Args:
            source: Username or profile URL.
            max_results: Maximum tweets to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)
        page = await self._new_page()

        try:
            url = f"{TWITTER_BASE}/{username}"
            tweets = []

            # Set up response interception for API data
            api_responses = []

            async def handle_response(response):
                if "UserTweets" in response.url or "TweetDetail" in response.url:
                    try:
                        data = await response.json()
                        api_responses.append(data)
                    except Exception:
                        pass

            page.on("response", handle_response)

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Scroll to load more tweets
            scroll_count = 0
            while len(tweets) < limit and scroll_count < 20:
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(2000)
                scroll_count += 1

                # Parse tweets from API responses
                for resp_data in api_responses:
                    self._extract_tweets_from_api(resp_data, tweets, limit)
                api_responses.clear()

            # If API interception didn't work, fallback to HTML parsing
            if not tweets:
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                tweets = self._extract_tweets_from_html(soup, username, limit)

            results = []
            for tweet in tweets[:limit]:
                results.append(
                    self.make_result(ContentType.POST, tweet, url=tweet.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Twitter/X.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        page = await self._new_page()

        try:
            encoded_query = quote(query)
            url = f"{TWITTER_BASE}/search?q={encoded_query}&src=typed_query&f=live"

            tweets = []
            api_responses = []

            async def handle_response(response):
                if "SearchTimeline" in response.url or "adaptive" in response.url:
                    try:
                        data = await response.json()
                        api_responses.append(data)
                    except Exception:
                        pass

            page.on("response", handle_response)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            scroll_count = 0
            while len(tweets) < limit and scroll_count < 15:
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(2000)
                scroll_count += 1

                for resp_data in api_responses:
                    self._extract_tweets_from_api(resp_data, tweets, limit)
                api_responses.clear()

            if not tweets:
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                tweets = self._extract_tweets_from_html(soup, "", limit)

            results = []
            for tweet in tweets[:limit]:
                results.append(
                    self.make_result(ContentType.SEARCH, tweet, url=tweet.get("url", ""))
                )

            return results
        finally:
            await page.context.close()

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier.lstrip("@")

    def _extract_tweets_from_api(
        self, data: dict, tweets: list[dict], limit: int
    ):
        """Extract tweets from Twitter's internal API response."""
        if not isinstance(data, dict):
            return

        # Walk the nested JSON to find tweet objects
        self._walk_for_tweets(data, tweets, limit, set())

    def _walk_for_tweets(self, obj: Any, tweets: list[dict], limit: int, seen: set):
        if len(tweets) >= limit:
            return
        if isinstance(obj, dict):
            # Check if this looks like a tweet result
            legacy = obj.get("legacy")
            if isinstance(legacy, dict) and "full_text" in legacy:
                tweet_id = legacy.get("id_str", obj.get("rest_id", ""))
                if tweet_id and tweet_id not in seen:
                    seen.add(tweet_id)
                    user = obj.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                    tweet = {
                        "tweet_id": tweet_id,
                        "text": legacy.get("full_text", ""),
                        "author": user.get("screen_name", ""),
                        "author_name": user.get("name", ""),
                        "created_at": legacy.get("created_at", ""),
                        "retweet_count": legacy.get("retweet_count", 0),
                        "like_count": legacy.get("favorite_count", 0),
                        "reply_count": legacy.get("reply_count", 0),
                        "quote_count": legacy.get("quote_count", 0),
                        "bookmark_count": legacy.get("bookmark_count", 0),
                        "is_retweet": "retweeted_status_result" in legacy or legacy.get("full_text", "").startswith("RT @"),
                        "url": f"{TWITTER_BASE}/{user.get('screen_name', '')}/status/{tweet_id}",
                    }
                    # Extract media
                    media = legacy.get("extended_entities", {}).get("media", [])
                    tweet["media"] = [
                        {
                            "type": m.get("type", ""),
                            "url": m.get("media_url_https", ""),
                            "expanded_url": m.get("expanded_url", ""),
                        }
                        for m in media
                    ]
                    tweets.append(tweet)

            # Recurse into all dict values
            for v in obj.values():
                self._walk_for_tweets(v, tweets, limit, seen)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_for_tweets(item, tweets, limit, seen)

    def _extract_tweets_from_html(
        self, soup: BeautifulSoup, username: str, limit: int
    ) -> list[dict]:
        """Fallback HTML parsing for tweets."""
        tweets = []
        for article in soup.find_all("article", {"data-testid": "tweet"}):
            if len(tweets) >= limit:
                break

            text_div = article.find("div", {"data-testid": "tweetText"})
            text = text_div.get_text(strip=True) if text_div else ""

            # Find the time element for the tweet timestamp
            time_el = article.find("time")
            created_at = time_el.get("datetime", "") if time_el else ""

            # Find the tweet link
            tweet_link = ""
            if time_el:
                parent_a = time_el.find_parent("a")
                if parent_a:
                    tweet_link = f"{TWITTER_BASE}{parent_a.get('href', '')}"

            tweets.append({
                "text": text,
                "author": username,
                "created_at": created_at,
                "url": tweet_link,
            })

        return tweets

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip().replace(",", "")
        multiplier = 1
        if text.endswith("K"):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1000000
            text = text[:-1]
        elif text.endswith("B"):
            multiplier = 1000000000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw"):
            await self._pw.stop()
        await super().close()
