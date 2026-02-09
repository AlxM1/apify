"""Proxy rotation utility."""

import random
import logging

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Rotates through a list of proxies."""

    def __init__(self, proxies: list[str] | None = None):
        self._proxies = proxies or []
        self._index = 0
        self._failed: set[str] = set()

    def add(self, proxy: str):
        self._proxies.append(proxy)

    def add_many(self, proxies: list[str]):
        self._proxies.extend(proxies)

    def load_from_file(self, path: str):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    self._proxies.append(line)
        logger.info(f"Loaded {len(self._proxies)} proxies from {path}")

    def get_next(self) -> str | None:
        """Get the next proxy in rotation, skipping failed ones."""
        if not self._proxies:
            return None
        available = [p for p in self._proxies if p not in self._failed]
        if not available:
            logger.warning("All proxies have failed, resetting...")
            self._failed.clear()
            available = self._proxies
        proxy = available[self._index % len(available)]
        self._index += 1
        return proxy

    def get_random(self) -> str | None:
        """Get a random proxy, skipping failed ones."""
        if not self._proxies:
            return None
        available = [p for p in self._proxies if p not in self._failed]
        if not available:
            self._failed.clear()
            available = self._proxies
        return random.choice(available)

    def mark_failed(self, proxy: str):
        self._failed.add(proxy)
        logger.debug(f"Marked proxy as failed: {proxy}")

    @property
    def count(self) -> int:
        return len(self._proxies)

    @property
    def available_count(self) -> int:
        return len([p for p in self._proxies if p not in self._failed])
