"""Telegram scraper for public channels and groups.

No API key required for web preview scraping. For deeper access, uses Telethon.
Supports: public channel posts, channel info, search.
"""

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

TELEGRAM_WEB = "https://t.me"


class TelegramScraper(BaseScraper):
    """Telegram public channel scraper using web preview.

    Scrapes public channels via t.me web previews (no auth needed).

    Usage:
        scraper = TelegramScraper()
        results = await scraper.scrape_profile("durov")
        results = await scraper.scrape_posts("durov", max_results=20)
        results = await scraper.search("crypto", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "telegram"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Telegram channel/group profile.

        Args:
            identifier: Channel username or t.me URL.
        """
        username = self._normalize_username(identifier)
        url = f"{TELEGRAM_WEB}/s/{username}"

        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract channel info
        channel_info = soup.find("div", class_="tgme_channel_info")
        profile = {
            "username": username,
            "url": f"{TELEGRAM_WEB}/{username}",
        }

        if channel_info:
            title = channel_info.find("div", class_="tgme_channel_info_header_title")
            profile["title"] = title.get_text(strip=True) if title else username

            desc = channel_info.find("div", class_="tgme_channel_info_description")
            profile["description"] = desc.get_text(strip=True) if desc else ""

            # Extract subscriber count
            counters = channel_info.find_all("div", class_="tgme_channel_info_counter")
            for counter in counters:
                value = counter.find("span", class_="counter_value")
                label = counter.find("span", class_="counter_type")
                if value and label:
                    label_text = label.get_text(strip=True).lower()
                    count_text = value.get_text(strip=True)
                    if "subscriber" in label_text or "member" in label_text:
                        profile["subscriber_count"] = self._parse_count(count_text)
                    elif "photo" in label_text:
                        profile["photo_count"] = self._parse_count(count_text)
                    elif "video" in label_text:
                        profile["video_count"] = self._parse_count(count_text)

            avatar = channel_info.find("img", class_="tgme_page_photo_image")
            if avatar:
                profile["avatar"] = avatar.get("src", "")
        else:
            profile["title"] = self._meta(soup, "og:title") or username
            profile["description"] = self._meta(soup, "og:description") or ""
            profile["avatar"] = self._meta(soup, "og:image") or ""

        return [self.make_result(ContentType.PROFILE, profile, url=profile["url"])]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a public Telegram channel.

        Args:
            source: Channel username or t.me URL.
            max_results: Maximum posts.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)

        results = []
        before = None

        while len(results) < limit:
            url = f"{TELEGRAM_WEB}/s/{username}"
            if before:
                url += f"?before={before}"

            resp = await self.fetch(url)
            soup = BeautifulSoup(resp.text, "lxml")

            messages = soup.find_all("div", class_="tgme_widget_message")
            if not messages:
                break

            for msg in messages:
                if len(results) >= limit:
                    break
                post = self._extract_message(msg, username)
                if post:
                    results.append(
                        self.make_result(ContentType.MESSAGE, post, url=post.get("url", ""))
                    )

            # Get the "before" parameter for pagination
            load_more = soup.find("a", class_="tme_messages_more")
            if load_more and load_more.get("href"):
                href = load_more["href"]
                match = re.search(r"before=(\d+)", href)
                if match:
                    new_before = match.group(1)
                    if new_before == before:
                        break
                    before = new_before
                else:
                    break
            else:
                break

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Telegram channels (limited - uses tgstat-like web search).

        Note: Telegram doesn't have a public search API for message content.
        This searches for channels/groups matching the query.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Use Telegram's built-in channel search via web
        # This is limited but works without auth
        search_url = f"https://t.me/s/{query}"

        try:
            resp = await self.fetch(search_url)
            soup = BeautifulSoup(resp.text, "lxml")

            results = []
            messages = soup.find_all("div", class_="tgme_widget_message")
            for msg in messages[:limit]:
                post = self._extract_message(msg, query)
                if post:
                    results.append(
                        self.make_result(ContentType.SEARCH, post, url=post.get("url", ""))
                    )

            return results
        except Exception as e:
            logger.warning(f"Telegram search failed: {e}")
            return []

    def _extract_message(self, msg_div, channel: str) -> dict | None:
        """Extract a message from the HTML widget."""
        msg_id_attr = msg_div.get("data-post", "")
        if "/" in msg_id_attr:
            msg_id = msg_id_attr.split("/")[-1]
        else:
            msg_id = msg_id_attr

        # Text content
        text_div = msg_div.find("div", class_="tgme_widget_message_text")
        text = text_div.get_text(separator="\n", strip=True) if text_div else ""

        # Date
        time_el = msg_div.find("time")
        datetime_str = time_el.get("datetime", "") if time_el else ""

        # Views
        views_span = msg_div.find("span", class_="tgme_widget_message_views")
        views = self._parse_count(views_span.get_text(strip=True)) if views_span else 0

        # Media
        photos = []
        for photo_wrap in msg_div.find_all("a", class_="tgme_widget_message_photo_wrap"):
            style = photo_wrap.get("style", "")
            img_match = re.search(r"url\('([^']+)'\)", style)
            if img_match:
                photos.append(img_match.group(1))

        videos = []
        for video_el in msg_div.find_all("video"):
            src = video_el.get("src", "")
            if src:
                videos.append(src)

        # Forward info
        fwd = msg_div.find("a", class_="tgme_widget_message_forwarded_from_name")
        forwarded_from = fwd.get_text(strip=True) if fwd else None

        if not text and not photos and not videos:
            return None

        return {
            "message_id": msg_id,
            "channel": channel,
            "text": text,
            "datetime": datetime_str,
            "views": views,
            "photos": photos,
            "videos": videos,
            "forwarded_from": forwarded_from,
            "url": f"{TELEGRAM_WEB}/{msg_id_attr}" if msg_id_attr else "",
        }

    def _normalize_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            path = identifier.rstrip("/").split("/")
            # Remove /s/ if present
            return [p for p in path if p and p != "s" and "t.me" not in p][-1]
        return identifier.lstrip("@")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip().replace(",", "").replace(" ", "")
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
