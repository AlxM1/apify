"""Stealth HTTP session and browser helpers for anti-bot evasion."""

import random
import logging

import httpx
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

# Common accept-language values
_ACCEPT_LANGS = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,de;q=0.8",
]

# Common sec-ch-ua values
_SEC_CH_UA = [
    '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
    '"Chromium";v="130", "Google Chrome";v="130", "Not_A Brand";v="99"',
    '"Chromium";v="129", "Google Chrome";v="129", "Not_A Brand";v="24"',
]


class StealthSession:
    """Creates httpx clients with randomized, realistic browser fingerprints."""

    def __init__(self):
        self._ua = UserAgent(browsers=["chrome", "edge"])

    def get_headers(self) -> dict[str, str]:
        """Generate a set of realistic browser headers."""
        return {
            "User-Agent": self._ua.random,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": random.choice(_ACCEPT_LANGS),
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": random.choice(_SEC_CH_UA),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def create_client(
        self, proxy: str | None = None, timeout: int = 30
    ) -> httpx.AsyncClient:
        """Create an httpx client with stealth headers."""
        kwargs = {
            "headers": self.get_headers(),
            "timeout": timeout,
            "follow_redirects": True,
            "http2": True,
        }
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    async def playwright_stealth_config() -> dict:
        """Return Playwright launch/context args for stealth browsing."""
        return {
            "launch_args": {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                ],
            },
            "context_args": {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "java_script_enabled": True,
            },
            "stealth_scripts": [
                # Override navigator.webdriver
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
                # Override chrome runtime
                "window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}}",
                # Override permissions
                """
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({state: Notification.permission})
                        : originalQuery(parameters);
                """,
                # Override plugins
                """
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                """,
                # Override languages
                """
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                """,
            ],
        }
