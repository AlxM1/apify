"""Discord scraper for public server information.

No API key required for discovery and invite endpoints.
Supports: server info, public server discovery, search.
"""

import logging
import re
from typing import Any

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
DISCORD_BASE = "https://discord.com"


class DiscordScraper(BaseScraper):
    """Discord scraper using public API endpoints.

    Scrapes publicly available Discord server information via invite links
    and the server discovery API. No bot token required.

    Usage:
        scraper = DiscordScraper()
        results = await scraper.scrape_profile("minecraft")  # invite code
        results = await scraper.scrape_posts("discoverable", max_results=20)
        results = await scraper.search("gaming", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "discord"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape Discord server info from an invite link.

        Args:
            identifier: Invite code, invite URL, or server ID.
        """
        invite_code = self._normalize_invite(identifier)

        url = f"{DISCORD_API}/invites/{invite_code}?with_counts=true&with_expiration=true"
        data = await self.fetch_json(url)

        guild = data.get("guild", {})
        server = {
            "server_id": guild.get("id", ""),
            "name": guild.get("name", ""),
            "description": guild.get("description", ""),
            "icon": f"https://cdn.discordapp.com/icons/{guild.get('id')}/{guild.get('icon')}.png"
                if guild.get("icon") else "",
            "banner": f"https://cdn.discordapp.com/banners/{guild.get('id')}/{guild.get('banner')}.png"
                if guild.get("banner") else "",
            "splash": f"https://cdn.discordapp.com/splashes/{guild.get('id')}/{guild.get('splash')}.png"
                if guild.get("splash") else "",
            "member_count": data.get("approximate_member_count", 0),
            "online_count": data.get("approximate_presence_count", 0),
            "verification_level": guild.get("verification_level", 0),
            "features": guild.get("features", []),
            "nsfw": guild.get("nsfw", False),
            "nsfw_level": guild.get("nsfw_level", 0),
            "premium_tier": guild.get("premium_tier", 0),
            "vanity_url": guild.get("vanity_url_code"),
            "invite_url": f"{DISCORD_BASE}/invite/{invite_code}",
            "invite_channel": data.get("channel", {}).get("name", ""),
            "inviter": data.get("inviter", {}).get("username", "") if data.get("inviter") else None,
        }

        return [self.make_result(ContentType.PROFILE, server, url=server["invite_url"])]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape discoverable servers.

        Args:
            source: Category or "discoverable" for featured servers.
            max_results: Maximum servers to fetch.
        """
        limit = max_results or self.config.max_results

        # Use Discord's server discovery endpoint
        url = f"{DISCORD_API}/discoverable-guilds"
        params = {"limit": min(48, limit), "offset": 0}

        try:
            data = await self.fetch_json(url, params=params)
            guilds = data.get("guilds", [])
        except Exception:
            # Discovery endpoint may require auth, fallback to widget API
            logger.info("Discovery endpoint unavailable without auth, using web scraping")
            return await self._scrape_discovery_web(source, limit)

        results = []
        for guild in guilds[:limit]:
            server = {
                "server_id": guild.get("id", ""),
                "name": guild.get("name", ""),
                "description": guild.get("description", ""),
                "member_count": guild.get("approximate_member_count", 0),
                "online_count": guild.get("approximate_presence_count", 0),
                "features": guild.get("features", []),
                "icon": f"https://cdn.discordapp.com/icons/{guild.get('id')}/{guild.get('icon')}.png"
                    if guild.get("icon") else "",
                "url": f"{DISCORD_BASE}/servers/{guild.get('id', '')}",
            }
            results.append(
                self.make_result(ContentType.CHANNEL, server, url=server["url"])
            )

        return results

    async def scrape_widget(self, server_id: str) -> list[ScraperResult]:
        """Scrape server info from the widget API (if enabled).

        Args:
            server_id: Discord server ID.
        """
        url = f"{DISCORD_API}/guilds/{server_id}/widget.json"

        try:
            data = await self.fetch_json(url)
        except Exception:
            logger.warning(f"Widget not enabled for server {server_id}")
            return []

        server = {
            "server_id": data.get("id", server_id),
            "name": data.get("name", ""),
            "instant_invite": data.get("instant_invite", ""),
            "online_count": data.get("presence_count", 0),
            "channels": [
                {"id": ch.get("id", ""), "name": ch.get("name", ""), "position": ch.get("position", 0)}
                for ch in data.get("channels", [])
            ],
            "members_online": [
                {
                    "id": m.get("id", ""),
                    "username": m.get("username", ""),
                    "status": m.get("status", ""),
                    "avatar_url": m.get("avatar_url", ""),
                }
                for m in data.get("members", [])[:50]
            ],
        }

        return [self.make_result(ContentType.CHANNEL, server, url=f"{DISCORD_BASE}/servers/{server_id}")]

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search for Discord servers.

        Uses Discord's server discovery search.

        Args:
            query: Search query.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        url = f"{DISCORD_API}/discoverable-guilds"
        params = {"query": query, "limit": min(48, limit)}

        try:
            data = await self.fetch_json(url, params=params)
            guilds = data.get("guilds", data.get("results", []))
        except Exception:
            return await self._search_web(query, limit)

        results = []
        for guild in guilds[:limit]:
            server = {
                "server_id": guild.get("id", ""),
                "name": guild.get("name", ""),
                "description": guild.get("description", ""),
                "member_count": guild.get("approximate_member_count", 0),
                "features": guild.get("features", []),
            }
            results.append(
                self.make_result(ContentType.SEARCH, server, url=f"{DISCORD_BASE}/servers/{server['server_id']}")
            )

        return results

    async def _scrape_discovery_web(self, category: str, limit: int) -> list[ScraperResult]:
        """Fallback: scrape discovery from the web."""
        from bs4 import BeautifulSoup

        url = f"{DISCORD_BASE}/servers"
        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        results = []
        for card in soup.find_all("div", class_=re.compile(r"server|guild")):
            name_el = card.find(["h3", "h4", "a"])
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            link = card.find("a", href=True)
            href = link["href"] if link else ""

            results.append(
                self.make_result(
                    ContentType.CHANNEL,
                    {"name": name, "url": f"{DISCORD_BASE}{href}" if href else ""},
                    url=f"{DISCORD_BASE}{href}" if href else "",
                )
            )
            if len(results) >= limit:
                break

        return results

    async def _search_web(self, query: str, limit: int) -> list[ScraperResult]:
        """Fallback web search."""
        return await self._scrape_discovery_web(query, limit)

    def _normalize_invite(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = identifier.rstrip("/").split("/")
            return parts[-1]
        return identifier
