"""Quora scraper using web scraping.

No API key required. Scrapes public questions, answers, profiles.
Supports: profiles, questions/answers, search, topics.
"""

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType
from scrapers.utils.stealth import StealthSession

logger = logging.getLogger(__name__)

QUORA_BASE = "https://www.quora.com"


class QuoraScraper(BaseScraper):
    """Quora scraper using web scraping with stealth headers.

    Usage:
        scraper = QuoraScraper()
        results = await scraper.scrape_profile("Adam-DAngelo")
        results = await scraper.scrape_posts("What-is-Python", max_results=20)
        results = await scraper.search("machine learning", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)
        self._stealth = StealthSession()

    @property
    def platform_name(self) -> str:
        return "quora"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Quora user profile.

        Args:
            identifier: Username or profile URL.
        """
        username = self._normalize_username(identifier)
        url = f"{QUORA_BASE}/profile/{username}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            profile = {
                "username": username,
                "name": self._meta(soup, "og:title") or username,
                "description": self._meta(soup, "og:description") or "",
                "image": self._meta(soup, "og:image") or "",
                "url": url,
            }

            # Try to extract stats from page
            self._extract_profile_stats(soup, profile)

            return [self.make_result(ContentType.PROFILE, profile, url=url)]
        finally:
            await client.aclose()

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape answers for a question or from a user profile.

        Args:
            source: Question slug, user profile slug, or URL.
            max_results: Maximum answers.
        """
        limit = max_results or self.config.max_results

        if source.startswith("http"):
            url = source
        elif "/" not in source and "-" in source and source[0].isupper():
            # Looks like a question slug
            url = f"{QUORA_BASE}/{source}"
        else:
            # Assume it's a username
            url = f"{QUORA_BASE}/profile/{source}/answers"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results = []

            # Find answer blocks
            for answer_div in soup.find_all("div", class_=re.compile(r"Answer|answer")):
                if len(results) >= limit:
                    break

                text_span = answer_div.find("span", class_=re.compile(r"content|CssComponent"))
                if not text_span:
                    continue
                text = text_span.get_text(separator="\n", strip=True)
                if not text or len(text) < 20:
                    continue

                # Try to find author
                author_link = answer_div.find("a", href=re.compile(r"/profile/"))
                author = ""
                if author_link:
                    author = author_link.get_text(strip=True)

                # Upvote count
                upvotes = 0
                upvote_el = answer_div.find(string=re.compile(r"\d+[KMB]?\s*(upvote|view)", re.I))
                if upvote_el:
                    match = re.search(r"([\d,.]+[KMB]?)", str(upvote_el))
                    if match:
                        upvotes = self._parse_count(match.group(1))

                answer = {
                    "text": text[:5000],
                    "author": author,
                    "upvotes": upvotes,
                    "url": url,
                }
                results.append(
                    self.make_result(ContentType.POST, answer, url=url)
                )

            # If no answer divs found, try generic content extraction
            if not results:
                results = self._extract_from_json_data(soup, limit)

            return results[:limit]
        finally:
            await client.aclose()

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Quora.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        url = f"{QUORA_BASE}/search?q={query}"

        client = self._stealth.create_client(proxy=self.config.proxy)
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results = []

            # Find question links in search results
            for link in soup.find_all("a", href=True):
                if len(results) >= limit:
                    break
                href = link["href"]
                # Quora question URLs typically have the pattern /Question-Text
                if re.match(r"^/[A-Z].*[^/]$", href) and "profile" not in href and "topic" not in href:
                    title = link.get_text(strip=True)
                    if title and len(title) > 10:
                        question = {
                            "title": title,
                            "url": f"{QUORA_BASE}{href}" if not href.startswith("http") else href,
                        }
                        results.append(
                            self.make_result(ContentType.SEARCH, question, url=question["url"])
                        )

            return results[:limit]
        finally:
            await client.aclose()

    def _extract_profile_stats(self, soup: BeautifulSoup, profile: dict):
        """Try to extract follower counts and answer counts from the profile page."""
        text = soup.get_text()
        followers_match = re.search(r"([\d,.]+[KMB]?)\s*(?:followers|Followers)", text)
        if followers_match:
            profile["follower_count"] = self._parse_count(followers_match.group(1))

        answers_match = re.search(r"([\d,.]+)\s*(?:answers|Answers)", text)
        if answers_match:
            profile["answer_count"] = self._parse_count(answers_match.group(1))

    def _extract_from_json_data(self, soup: BeautifulSoup, limit: int) -> list[ScraperResult]:
        """Try to extract data from embedded JSON in the page."""
        results = []
        for script in soup.find_all("script", {"type": "application/json"}):
            if script.string and len(results) < limit:
                try:
                    data = json.loads(script.string)
                    self._walk_for_answers(data, results, limit)
                except json.JSONDecodeError:
                    continue
        return results

    def _walk_for_answers(self, data: Any, results: list[ScraperResult], limit: int):
        if len(results) >= limit:
            return
        if isinstance(data, dict):
            text = data.get("text") or data.get("content")
            author = data.get("authorName") or data.get("author", {}).get("name", "") if isinstance(data.get("author"), dict) else ""
            if isinstance(text, str) and len(text) > 50 and author:
                answer = {
                    "text": text[:5000],
                    "author": author,
                    "upvotes": data.get("upvoteCount", 0),
                }
                results.append(self.make_result(ContentType.POST, answer))

            for v in data.values():
                self._walk_for_answers(v, results, limit)
        elif isinstance(data, list):
            for item in data:
                self._walk_for_answers(item, results, limit)

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            if "profile" in parts:
                idx = parts.index("profile")
                return parts[idx + 1] if idx + 1 < len(parts) else identifier
            return parts[-1]
        return identifier

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip().replace(",", "")
        multiplier = 1
        if text.endswith("K"):
            multiplier, text = 1000, text[:-1]
        elif text.endswith("M"):
            multiplier, text = 1000000, text[:-1]
        elif text.endswith("B"):
            multiplier, text = 1000000000, text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0
