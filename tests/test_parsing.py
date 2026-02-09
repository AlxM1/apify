"""Tests for data parsing and URL normalization across all scrapers.

These tests exercise the internal extraction logic without any network calls,
by feeding mock API responses and HTML through each scraper's parsers.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.base import ScraperConfig


# ============================================================
# Reddit
# ============================================================

class TestRedditParsing:
    def _scraper(self):
        from scrapers.reddit import RedditScraper
        return RedditScraper()

    def test_extract_username_from_url(self):
        s = self._scraper()
        assert s._extract_username("https://www.reddit.com/user/spez") == "spez"
        assert s._extract_username("https://old.reddit.com/u/spez/") == "spez"
        assert s._extract_username("u/testuser") == "testuser"
        assert s._extract_username("rawname") == "rawname"

    def test_build_listing_url(self):
        s = self._scraper()
        assert s._build_listing_url("r/python").endswith("/r/python/hot.json")
        assert s._build_listing_url("u/spez").endswith("/u/spez/submitted.json")
        assert s._build_listing_url("https://reddit.com/r/news").endswith(".json")

    def test_extract_post_data(self):
        s = self._scraper()
        mock_post = {
            "id": "abc123",
            "title": "Test Post",
            "author": "testuser",
            "subreddit": "python",
            "selftext": "body text",
            "url": "https://example.com",
            "permalink": "/r/python/comments/abc123/test/",
            "score": 42,
            "upvote_ratio": 0.95,
            "num_comments": 10,
            "created_utc": 1700000000,
            "is_video": False,
            "is_self": True,
            "over_18": False,
            "spoiler": False,
            "stickied": False,
            "link_flair_text": "Discussion",
            "thumbnail": "",
            "domain": "self.python",
            "total_awards_received": 2,
        }
        result = s._extract_post_data(mock_post)
        assert result["post_id"] == "abc123"
        assert result["title"] == "Test Post"
        assert result["author"] == "testuser"
        assert result["score"] == 42
        assert result["awards"] == 2

    def test_flatten_comments(self):
        s = self._scraper()
        mock_children = [
            {
                "kind": "t1",
                "data": {
                    "id": "c1",
                    "author": "user1",
                    "body": "top comment",
                    "score": 10,
                    "created_utc": 1700000000,
                    "is_submitter": False,
                    "parent_id": "t3_abc",
                    "total_awards_received": 0,
                    "replies": {
                        "data": {
                            "children": [
                                {
                                    "kind": "t1",
                                    "data": {
                                        "id": "c2",
                                        "author": "user2",
                                        "body": "reply",
                                        "score": 5,
                                        "created_utc": 1700000001,
                                        "is_submitter": True,
                                        "parent_id": "t1_c1",
                                        "total_awards_received": 0,
                                        "replies": "",
                                    }
                                }
                            ]
                        }
                    },
                }
            }
        ]
        results = []
        s._flatten_comments(mock_children, results, limit=10)
        assert len(results) == 2
        assert results[0].data["body"] == "top comment"
        assert results[0].data["depth"] == 0
        assert results[1].data["body"] == "reply"
        assert results[1].data["depth"] == 1


# ============================================================
# Bluesky
# ============================================================

class TestBlueskyParsing:
    def _scraper(self):
        from scrapers.bluesky import BlueskyScraper
        return BlueskyScraper()

    def test_normalize_handle(self):
        s = self._scraper()
        assert s._normalize_handle("jay.bsky.team") == "jay.bsky.team"
        assert s._normalize_handle("@jay.bsky.team") == "jay.bsky.team"
        assert s._normalize_handle("https://bsky.app/profile/jay.bsky.team") == "jay.bsky.team"

    def test_extract_post_data(self):
        s = self._scraper()
        mock_post = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
            "cid": "bafyabc",
            "author": {
                "did": "did:plc:abc",
                "handle": "test.bsky.social",
                "displayName": "Test User",
            },
            "record": {
                "text": "Hello Bluesky!",
                "createdAt": "2024-01-15T10:00:00Z",
            },
            "likeCount": 42,
            "repostCount": 5,
            "replyCount": 3,
            "quoteCount": 1,
            "labels": [],
            "embed": {},
        }
        result = s._extract_post_data(mock_post)
        assert result["text"] == "Hello Bluesky!"
        assert result["author_handle"] == "test.bsky.social"
        assert result["like_count"] == 42
        assert result["url"] == "https://bsky.app/profile/test.bsky.social/post/xyz"


# ============================================================
# HackerNews
# ============================================================

class TestHackerNewsParsing:
    def _scraper(self):
        from scrapers.hackernews import HackerNewsScraper
        return HackerNewsScraper()

    def test_extract_story_data(self):
        s = self._scraper()
        mock_item = {
            "id": 12345,
            "title": "Show HN: My Project",
            "url": "https://example.com/project",
            "by": "testuser",
            "score": 150,
            "descendants": 42,
            "time": 1700000000,
            "text": "",
            "type": "story",
        }
        result = s._extract_story_data(mock_item)
        assert result["story_id"] == 12345
        assert result["title"] == "Show HN: My Project"
        assert result["author"] == "testuser"
        assert result["score"] == 150
        assert result["num_comments"] == 42


# ============================================================
# Twitter
# ============================================================

class TestTwitterParsing:
    def _scraper(self):
        from scrapers.twitter import TwitterScraper
        return TwitterScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("elonmusk") == "elonmusk"
        assert s._normalize_username("@elonmusk") == "elonmusk"
        assert s._normalize_username("https://x.com/elonmusk") == "elonmusk"

    def test_parse_count(self):
        from scrapers.twitter import TwitterScraper
        assert TwitterScraper._parse_count("1,234") == 1234
        assert TwitterScraper._parse_count("5.2K") == 5200
        assert TwitterScraper._parse_count("1.5M") == 1500000
        assert TwitterScraper._parse_count("2B") == 2000000000

    def test_walk_for_tweets(self):
        s = self._scraper()
        mock_api = {
            "data": {
                "timeline": {
                    "instructions": [
                        {
                            "entries": [
                                {
                                    "content": {
                                        "itemContent": {
                                            "tweet_results": {
                                                "result": {
                                                    "rest_id": "123456",
                                                    "legacy": {
                                                        "id_str": "123456",
                                                        "full_text": "Hello Twitter!",
                                                        "created_at": "Mon Jan 15 10:00:00 +0000 2024",
                                                        "retweet_count": 10,
                                                        "favorite_count": 50,
                                                        "reply_count": 3,
                                                        "quote_count": 2,
                                                        "bookmark_count": 1,
                                                    },
                                                    "core": {
                                                        "user_results": {
                                                            "result": {
                                                                "legacy": {
                                                                    "screen_name": "testuser",
                                                                    "name": "Test User",
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                }
            }
        }
        tweets = []
        s._walk_for_tweets(mock_api, tweets, 10, set())
        assert len(tweets) == 1
        assert tweets[0]["text"] == "Hello Twitter!"
        assert tweets[0]["author"] == "testuser"
        assert tweets[0]["like_count"] == 50
        assert tweets[0]["retweet_count"] == 10


# ============================================================
# Instagram
# ============================================================

class TestInstagramParsing:
    def _scraper(self):
        from scrapers.instagram import InstagramScraper
        return InstagramScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("instagram") == "instagram"
        assert s._normalize_username("@instagram") == "instagram"
        assert s._normalize_username("https://www.instagram.com/instagram/") == "instagram"

    def test_get_caption(self):
        from scrapers.instagram import InstagramScraper
        # GraphQL style
        assert InstagramScraper._get_caption({
            "edge_media_to_caption": {"edges": [{"node": {"text": "Hello!"}}]}
        }) == "Hello!"
        # API style
        assert InstagramScraper._get_caption({"caption": {"text": "World"}}) == "World"
        # String caption
        assert InstagramScraper._get_caption({"caption": "Direct"}) == "Direct"
        # Empty
        assert InstagramScraper._get_caption({}) == ""

    def test_parse_count(self):
        from scrapers.instagram import InstagramScraper
        assert InstagramScraper._parse_count("1,234") == 1234
        assert InstagramScraper._parse_count("5.2K") == 5200
        assert InstagramScraper._parse_count("1.5M") == 1500000


# ============================================================
# TikTok
# ============================================================

class TestTikTokParsing:
    def _scraper(self):
        from scrapers.tiktok import TikTokScraper
        return TikTokScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("tiktok") == "tiktok"
        assert s._normalize_username("@tiktok") == "tiktok"
        assert s._normalize_username("https://www.tiktok.com/@tiktok") == "tiktok"

    def test_extract_videos_from_api(self):
        s = self._scraper()
        mock_data = {
            "itemList": [
                {
                    "id": "7001",
                    "desc": "Funny video #comedy",
                    "stats": {
                        "playCount": 1000000,
                        "diggCount": 50000,
                        "commentCount": 500,
                        "shareCount": 200,
                        "collectCount": 100,
                    },
                    "author": {"uniqueId": "testuser", "nickname": "Test"},
                    "video": {"duration": 30, "cover": "https://img.com/cover.jpg"},
                    "music": {"title": "Original Sound", "authorName": "Test"},
                    "challenges": [{"hashtagName": "comedy"}],
                    "createTime": 1700000000,
                }
            ]
        }
        videos = []
        s._extract_videos_from_api(mock_data, videos, 10)
        assert len(videos) == 1
        assert videos[0]["video_id"] == "7001"
        assert videos[0]["description"] == "Funny video #comedy"
        assert videos[0]["play_count"] == 1000000
        assert videos[0]["like_count"] == 50000
        assert videos[0]["hashtags"] == ["comedy"]

    def test_find_nested(self):
        from scrapers.tiktok import TikTokScraper
        data = {"a": {"b": {"c": 42}}}
        assert TikTokScraper._find_nested(data, ["a", "b", "c"]) == 42
        assert TikTokScraper._find_nested(data, ["a", "x"]) is None


# ============================================================
# Pinterest
# ============================================================

class TestPinterestParsing:
    def _scraper(self):
        from scrapers.pinterest import PinterestScraper
        return PinterestScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("pinterest") == "pinterest"
        assert s._normalize_username("@pinterest") == "pinterest"
        assert s._normalize_username("https://www.pinterest.com/testuser/") == "testuser"

    def test_find_pins_in_data(self):
        s = self._scraper()
        mock_data = {
            "results": [
                {
                    "id": "999",
                    "type": "pin",
                    "title": "Great Pin",
                    "description": "A cool pin",
                    "images": {"orig": {"url": "https://img.com/pin.jpg"}},
                    "link": "https://example.com",
                    "dominant_color": "#ff0000",
                    "aggregated_pin_data": {"aggregated_stats": {"saves": 100}},
                    "comment_count": 5,
                    "pinner": {"username": "testuser"},
                    "board": {"name": "My Board"},
                }
            ]
        }
        pins = []
        s._find_pins_in_data(mock_data, pins, 10, set())
        assert len(pins) == 1
        assert pins[0]["pin_id"] == "999"
        assert pins[0]["title"] == "Great Pin"
        assert pins[0]["save_count"] == 100


# ============================================================
# Mastodon
# ============================================================

class TestMastodonParsing:
    def _scraper(self):
        from scrapers.mastodon import MastodonScraper
        return MastodonScraper()

    def test_parse_identifier(self):
        s = self._scraper()
        inst, user = s._parse_identifier("Gargron@mastodon.social")
        assert inst == "https://mastodon.social"
        assert user == "Gargron"

        inst, user = s._parse_identifier("https://mastodon.social/@Gargron")
        assert inst == "https://mastodon.social"
        assert user == "Gargron"

        inst, user = s._parse_identifier("localuser")
        assert user == "localuser"

    def test_extract_toot(self):
        s = self._scraper()
        mock_status = {
            "id": "12345",
            "content": "<p>Hello <strong>world</strong>!</p>",
            "account": {"acct": "test@mastodon.social", "display_name": "Test"},
            "created_at": "2024-01-15T10:00:00Z",
            "url": "https://mastodon.social/@test/12345",
            "favourites_count": 10,
            "reblogs_count": 5,
            "replies_count": 2,
            "language": "en",
            "visibility": "public",
            "sensitive": False,
            "spoiler_text": "",
            "reblog": None,
            "media_attachments": [],
            "tags": [{"name": "python"}],
            "mentions": [{"acct": "other@example.com"}],
        }
        result = s._extract_toot(mock_status)
        assert result["toot_id"] == "12345"
        assert "Hello" in result["content"]
        assert "world" in result["content"]
        assert result["author"] == "test@mastodon.social"
        assert result["favourites_count"] == 10
        assert result["is_reblog"] is False
        assert result["tags"] == ["python"]

    def test_strip_html(self):
        from scrapers.mastodon import MastodonScraper
        assert MastodonScraper._strip_html("<p>Hello <b>world</b></p>") == "Hello world"


# ============================================================
# Telegram
# ============================================================

class TestTelegramParsing:
    def _scraper(self):
        from scrapers.telegram import TelegramScraper
        return TelegramScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("@durov") == "durov"
        assert s._normalize_username("https://t.me/durov") == "durov"
        assert s._normalize_username("https://t.me/s/durov") == "durov"

    def test_parse_count(self):
        from scrapers.telegram import TelegramScraper
        assert TelegramScraper._parse_count("1.5K") == 1500
        assert TelegramScraper._parse_count("2.3M") == 2300000
        assert TelegramScraper._parse_count("42") == 42


# ============================================================
# Twitch
# ============================================================

class TestTwitchParsing:
    def _scraper(self):
        from scrapers.twitch import TwitchScraper
        return TwitchScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("Shroud") == "shroud"
        assert s._normalize_username("@shroud") == "shroud"
        assert s._normalize_username("https://www.twitch.tv/shroud") == "shroud"


# ============================================================
# Kick
# ============================================================

class TestKickParsing:
    def _scraper(self):
        from scrapers.kick import KickScraper
        return KickScraper()

    def test_normalize_slug(self):
        s = self._scraper()
        assert s._normalize_slug("xqc") == "xqc"
        assert s._normalize_slug("@XQC") == "xqc"
        assert s._normalize_slug("https://kick.com/xqc") == "xqc"


# ============================================================
# Medium
# ============================================================

class TestMediumParsing:
    def _scraper(self):
        from scrapers.medium import MediumScraper
        return MediumScraper()

    def test_normalize_handle(self):
        s = self._scraper()
        assert s._normalize_handle("username") == "@username"
        assert s._normalize_handle("@username") == "@username"
        assert s._normalize_handle("https://medium.com/@username/article") == "@username"

    def test_build_rss_url(self):
        s = self._scraper()
        assert s._build_rss_url("@testuser") == "https://medium.com/feed/@testuser"
        assert s._build_rss_url("tag/python") == "https://medium.com/feed/tag/python"

    def test_parse_rss(self):
        s = self._scraper()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <title>Test Blog</title>
            <item>
              <title>Article One</title>
              <link>https://medium.com/@test/article-one</link>
              <description>&lt;p&gt;Hello world&lt;/p&gt;</description>
              <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
              <dc:creator>Test Author</dc:creator>
              <category>python</category>
              <category>programming</category>
            </item>
            <item>
              <title>Article Two</title>
              <link>https://medium.com/@test/article-two</link>
              <description>Short desc</description>
              <pubDate>Tue, 16 Jan 2024 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        results = s._parse_rss(xml, 10)
        assert len(results) == 2
        assert results[0].data["title"] == "Article One"
        assert results[0].data["author"] == "Test Author"
        assert results[0].data["tags"] == ["python", "programming"]
        assert results[1].data["title"] == "Article Two"


# ============================================================
# Tumblr
# ============================================================

class TestTumblrParsing:
    def _scraper(self):
        from scrapers.tumblr import TumblrScraper
        return TumblrScraper()

    def test_normalize_blog(self):
        s = self._scraper()
        assert s._normalize_blog("staff") == "staff"
        assert s._normalize_blog("https://staff.tumblr.com") == "staff"
        assert s._normalize_blog("staff.tumblr.com") == "staff"


# ============================================================
# Threads
# ============================================================

class TestThreadsParsing:
    def _scraper(self):
        from scrapers.threads import ThreadsScraper
        return ThreadsScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("zuck") == "zuck"
        assert s._normalize_username("@zuck") == "zuck"
        assert s._normalize_username("https://www.threads.net/@zuck") == "zuck"


# ============================================================
# Discord
# ============================================================

class TestDiscordParsing:
    def _scraper(self):
        from scrapers.discord import DiscordScraper
        return DiscordScraper()

    def test_normalize_invite(self):
        s = self._scraper()
        assert s._normalize_invite("minecraft") == "minecraft"
        assert s._normalize_invite("https://discord.gg/minecraft") == "minecraft"
        assert s._normalize_invite("https://discord.com/invite/abc123") == "abc123"


# ============================================================
# Quora
# ============================================================

class TestQuoraParsing:
    def _scraper(self):
        from scrapers.quora import QuoraScraper
        return QuoraScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("Adam-DAngelo") == "Adam-DAngelo"
        assert s._normalize_username("https://www.quora.com/profile/Adam-DAngelo") == "Adam-DAngelo"

    def test_parse_count(self):
        from scrapers.quora import QuoraScraper
        assert QuoraScraper._parse_count("1.5K") == 1500
        assert QuoraScraper._parse_count("42") == 42


# ============================================================
# Snapchat
# ============================================================

class TestSnapchatParsing:
    def _scraper(self):
        from scrapers.snapchat import SnapchatScraper
        return SnapchatScraper()

    def test_normalize_username(self):
        s = self._scraper()
        assert s._normalize_username("snapchat") == "snapchat"
        assert s._normalize_username("@snapchat") == "snapchat"
        assert s._normalize_username("https://www.snapchat.com/add/test") == "test"


# ============================================================
# Substack
# ============================================================

class TestSubstackParsing:
    def _scraper(self):
        from scrapers.substack import SubstackScraper
        return SubstackScraper()

    def test_resolve_base_url(self):
        s = self._scraper()
        result = s._resolve_base_url("platformer")
        assert "platformer" in result
        assert result == "https://platformer.substack.com"
        result = s._resolve_base_url("https://platformer.news/")
        assert "platformer" in result


# ============================================================
# Rumble
# ============================================================

class TestRumbleParsing:
    def _scraper(self):
        from scrapers.rumble import RumbleScraper
        return RumbleScraper()

    def test_normalize_channel(self):
        s = self._scraper()
        result = s._normalize_channel("testchannel")
        assert "testchannel" in result


# ============================================================
# Utils
# ============================================================

class TestProxyRotator:
    def test_basic_rotation(self):
        from scrapers.utils.proxy import ProxyRotator
        pr = ProxyRotator(["http://p1:8080", "http://p2:8080", "http://p3:8080"])
        assert pr.count == 3
        p1 = pr.get_next()
        p2 = pr.get_next()
        assert p1 != p2 or pr.count == 1

    def test_empty(self):
        from scrapers.utils.proxy import ProxyRotator
        pr = ProxyRotator()
        assert pr.get_next() is None
        assert pr.get_random() is None

    def test_mark_failed(self):
        from scrapers.utils.proxy import ProxyRotator
        pr = ProxyRotator(["http://p1:8080", "http://p2:8080"])
        pr.mark_failed("http://p1:8080")
        assert pr.available_count == 1

    def test_load_from_file(self):
        import tempfile
        from scrapers.utils.proxy import ProxyRotator
        pr = ProxyRotator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://p1:8080\n# comment\nhttp://p2:8080\n\n")
            f.flush()
            pr.load_from_file(f.name)
        assert pr.count == 2
        os.unlink(f.name)


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire(self):
        from scrapers.utils.rate_limiter import RateLimiter
        rl = RateLimiter(requests_per_second=100, burst=5)
        # Should be able to acquire 5 quickly (burst)
        for _ in range(5):
            await rl.acquire()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        from scrapers.utils.rate_limiter import RateLimiter
        rl = RateLimiter(requests_per_second=100, burst=1)
        async with rl:
            pass  # Should not raise


class TestExporter:
    def test_to_json(self):
        import tempfile
        from scrapers.utils.export import Exporter
        from scrapers.base import ScraperResult
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = Exporter(output_dir=tmpdir)
            results = [
                ScraperResult(platform="test", content_type="post", data={"text": "a"}),
                ScraperResult(platform="test", content_type="post", data={"text": "b"}),
            ]
            path = exp.to_json(results)
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 2

    def test_to_jsonl(self):
        import tempfile
        from scrapers.utils.export import Exporter
        from scrapers.base import ScraperResult
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = Exporter(output_dir=tmpdir)
            results = [
                ScraperResult(platform="test", content_type="post", data={"text": "a"}),
            ]
            path = exp.to_jsonl(results)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
