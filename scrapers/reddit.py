"""Reddit scraper using the built-in .json endpoint and PRAW.

No API key required for .json endpoint approach. PRAW requires a free Reddit app.
Supports: posts, comments, profiles, subreddits, search.
"""

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

# Reddit's .json endpoint works without authentication
REDDIT_BASE = "https://www.reddit.com"
OLD_REDDIT = "https://old.reddit.com"


class RedditScraper(BaseScraper):
    """Reddit scraper using the free .json endpoint.

    No API keys needed. Appends .json to Reddit URLs for structured data.

    Usage:
        scraper = RedditScraper()
        results = await scraper.scrape_profile("spez")
        results = await scraper.scrape_posts("r/python", max_results=50)
        results = await scraper.search("web scraping", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None):
        super().__init__(config)

    @property
    def platform_name(self) -> str:
        return "reddit"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Reddit user profile.

        Args:
            identifier: Username (with or without u/ prefix) or profile URL.
        """
        username = self._extract_username(identifier)
        url = f"{REDDIT_BASE}/user/{username}/about.json"

        data = await self.fetch_json(url)
        user_data = data.get("data", {})

        profile = {
            "username": user_data.get("name", username),
            "display_name": user_data.get("subreddit", {}).get("title", ""),
            "description": user_data.get("subreddit", {}).get("public_description", ""),
            "karma_post": user_data.get("link_karma", 0),
            "karma_comment": user_data.get("comment_karma", 0),
            "karma_total": user_data.get("total_karma", 0),
            "created_utc": user_data.get("created_utc"),
            "is_gold": user_data.get("is_gold", False),
            "is_mod": user_data.get("is_mod", False),
            "verified": user_data.get("verified", False),
            "icon_img": user_data.get("icon_img", ""),
            "profile_url": f"{REDDIT_BASE}/user/{username}",
        }

        return [
            self.make_result(
                ContentType.PROFILE,
                profile,
                url=f"{REDDIT_BASE}/user/{username}",
            )
        ]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape posts from a subreddit, user, or URL.

        Args:
            source: Subreddit name (r/python), username (u/spez), or Reddit URL.
            max_results: Maximum posts to fetch.
        """
        limit = max_results or self.config.max_results
        url = self._build_listing_url(source)

        results = []
        after = None

        while len(results) < limit:
            batch_url = f"{url}?limit=100&raw_json=1"
            if after:
                batch_url += f"&after={after}"

            data = await self.fetch_json(batch_url)
            listing = data.get("data", {})
            children = listing.get("children", [])

            if not children:
                break

            for child in children:
                if len(results) >= limit:
                    break
                post = child.get("data", {})
                post_data = self._extract_post_data(post)
                results.append(
                    self.make_result(
                        ContentType.POST,
                        post_data,
                        url=f"{REDDIT_BASE}{post.get('permalink', '')}",
                    )
                )

            after = listing.get("after")
            if not after:
                break

        return results

    async def scrape_comments(
        self, post_url: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape comments from a Reddit post.

        Args:
            post_url: Full Reddit post URL or post ID.
        """
        limit = max_results or self.config.max_results

        if post_url.startswith("http"):
            url = post_url.rstrip("/") + ".json?raw_json=1"
        else:
            url = f"{REDDIT_BASE}/comments/{post_url}.json?raw_json=1"

        data = await self.fetch_json(url)

        if not isinstance(data, list) or len(data) < 2:
            return []

        comments_listing = data[1].get("data", {}).get("children", [])
        results = []
        self._flatten_comments(comments_listing, results, limit)

        return results

    async def scrape_subreddit_info(self, subreddit: str) -> list[ScraperResult]:
        """Scrape subreddit metadata.

        Args:
            subreddit: Subreddit name (with or without r/ prefix).
        """
        sub = subreddit.replace("r/", "").strip("/")
        url = f"{REDDIT_BASE}/r/{sub}/about.json"

        data = await self.fetch_json(url)
        sub_data = data.get("data", {})

        info = {
            "name": sub_data.get("display_name", sub),
            "title": sub_data.get("title", ""),
            "description": sub_data.get("public_description", ""),
            "description_full": sub_data.get("description", ""),
            "subscribers": sub_data.get("subscribers", 0),
            "active_users": sub_data.get("accounts_active", 0),
            "created_utc": sub_data.get("created_utc"),
            "nsfw": sub_data.get("over18", False),
            "subreddit_type": sub_data.get("subreddit_type", ""),
            "icon_img": sub_data.get("icon_img", ""),
            "banner_img": sub_data.get("banner_background_image", ""),
            "url": f"{REDDIT_BASE}/r/{sub}",
        }

        return [
            self.make_result(ContentType.CHANNEL, info, url=f"{REDDIT_BASE}/r/{sub}")
        ]

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Reddit.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results
        url = f"{REDDIT_BASE}/search.json?q={query}&limit={min(limit, 100)}&raw_json=1&sort=relevance"

        data = await self.fetch_json(url)
        children = data.get("data", {}).get("children", [])

        results = []
        for child in children[:limit]:
            post = child.get("data", {})
            post_data = self._extract_post_data(post)
            results.append(
                self.make_result(
                    ContentType.SEARCH,
                    post_data,
                    url=f"{REDDIT_BASE}{post.get('permalink', '')}",
                )
            )

        return results

    def _extract_username(self, identifier: str) -> str:
        if identifier.startswith("http"):
            parts = urlparse(identifier).path.strip("/").split("/")
            if "user" in parts:
                idx = parts.index("user")
                return parts[idx + 1] if idx + 1 < len(parts) else identifier
            if "u" in parts:
                idx = parts.index("u")
                return parts[idx + 1] if idx + 1 < len(parts) else identifier
        return identifier.replace("u/", "").strip("/")

    def _build_listing_url(self, source: str) -> str:
        if source.startswith("http"):
            return source.rstrip("/") + ".json"
        if source.startswith("r/"):
            return f"{REDDIT_BASE}/{source}/hot.json"
        if source.startswith("u/"):
            return f"{REDDIT_BASE}/{source}/submitted.json"
        # Assume subreddit
        return f"{REDDIT_BASE}/r/{source}/hot.json"

    def _extract_post_data(self, post: dict) -> dict[str, Any]:
        return {
            "post_id": post.get("id", ""),
            "title": post.get("title", ""),
            "author": post.get("author", "[deleted]"),
            "subreddit": post.get("subreddit", ""),
            "selftext": post.get("selftext", ""),
            "url": post.get("url", ""),
            "permalink": post.get("permalink", ""),
            "score": post.get("score", 0),
            "upvote_ratio": post.get("upvote_ratio", 0),
            "num_comments": post.get("num_comments", 0),
            "created_utc": post.get("created_utc"),
            "is_video": post.get("is_video", False),
            "is_self": post.get("is_self", False),
            "over_18": post.get("over_18", False),
            "spoiler": post.get("spoiler", False),
            "stickied": post.get("stickied", False),
            "link_flair_text": post.get("link_flair_text"),
            "thumbnail": post.get("thumbnail", ""),
            "domain": post.get("domain", ""),
            "awards": post.get("total_awards_received", 0),
        }

    def _flatten_comments(
        self, children: list[dict], results: list[ScraperResult], limit: int, depth: int = 0
    ):
        for child in children:
            if len(results) >= limit:
                return
            if child.get("kind") != "t1":
                continue
            data = child.get("data", {})
            comment = {
                "comment_id": data.get("id", ""),
                "author": data.get("author", "[deleted]"),
                "body": data.get("body", ""),
                "score": data.get("score", 0),
                "created_utc": data.get("created_utc"),
                "depth": depth,
                "is_submitter": data.get("is_submitter", False),
                "parent_id": data.get("parent_id", ""),
                "awards": data.get("total_awards_received", 0),
            }
            results.append(
                self.make_result(
                    ContentType.COMMENT,
                    comment,
                    url=f"{REDDIT_BASE}{data.get('permalink', '')}",
                )
            )
            # Recurse into replies
            replies = data.get("replies")
            if isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                self._flatten_comments(reply_children, results, limit, depth + 1)
