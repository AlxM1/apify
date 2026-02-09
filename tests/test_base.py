"""Tests for the base scraper, config, export, and registry."""

import asyncio
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType


# --- Concrete test scraper ---

class DummyScraper(BaseScraper):
    @property
    def platform_name(self):
        return "dummy"

    async def scrape_profile(self, identifier):
        return [self.make_result(ContentType.PROFILE, {"name": identifier}, url=f"https://example.com/{identifier}")]

    async def scrape_posts(self, source, max_results=None):
        limit = max_results or self.config.max_results
        return [self.make_result(ContentType.POST, {"text": f"post {i}"}) for i in range(limit)]

    async def search(self, query, max_results=None):
        return [self.make_result(ContentType.SEARCH, {"query": query})]


# --- ScraperConfig tests ---

class TestScraperConfig:
    def test_defaults(self):
        c = ScraperConfig()
        assert c.max_results == 100
        assert c.proxy is None
        assert c.timeout == 30
        assert c.delay_between_requests == 1.0
        assert c.output_format == "json"
        assert c.headless is True

    def test_custom(self):
        c = ScraperConfig(max_results=10, proxy="http://proxy:8080", timeout=60)
        assert c.max_results == 10
        assert c.proxy == "http://proxy:8080"
        assert c.timeout == 60


# --- ScraperResult tests ---

class TestScraperResult:
    def test_to_dict(self):
        r = ScraperResult(platform="test", content_type="post", data={"text": "hello"}, url="https://x.com/1")
        d = r.to_dict()
        assert d["platform"] == "test"
        assert d["content_type"] == "post"
        assert d["data"]["text"] == "hello"
        assert d["url"] == "https://x.com/1"
        assert "scraped_at" in d
        assert "raw_data" not in d  # None should be stripped

    def test_to_dict_with_raw(self):
        r = ScraperResult(platform="test", content_type="post", data={}, raw_data={"k": "v"})
        d = r.to_dict()
        assert d["raw_data"]["k"] == "v"


# --- ContentType tests ---

class TestContentType:
    def test_values(self):
        assert ContentType.POST.value == "post"
        assert ContentType.PROFILE.value == "profile"
        assert ContentType.VIDEO.value == "video"
        assert ContentType.ARTICLE.value == "article"
        assert ContentType.COMMENT.value == "comment"
        assert ContentType.SEARCH.value == "search"


# --- BaseScraper tests ---

class TestBaseScraper:
    def test_make_result(self):
        s = DummyScraper()
        r = s.make_result(ContentType.POST, {"text": "hi"}, url="https://x.com/1")
        assert r.platform == "dummy"
        assert r.content_type == "post"
        assert r.data["text"] == "hi"
        assert len(s._results) == 1

    def test_make_result_string_type(self):
        s = DummyScraper()
        r = s.make_result("custom_type", {"a": 1})
        assert r.content_type == "custom_type"

    @pytest.mark.asyncio
    async def test_scrape_profile(self):
        s = DummyScraper()
        results = await s.scrape_profile("testuser")
        assert len(results) == 1
        assert results[0].data["name"] == "testuser"
        assert results[0].url == "https://example.com/testuser"

    @pytest.mark.asyncio
    async def test_scrape_posts_respects_limit(self):
        s = DummyScraper(ScraperConfig(max_results=5))
        results = await s.scrape_posts("source")
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search(self):
        s = DummyScraper()
        results = await s.search("test query")
        assert len(results) == 1
        assert results[0].data["query"] == "test query"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with DummyScraper() as s:
            results = await s.scrape_profile("user")
            assert len(results) == 1

    def test_export_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = DummyScraper(ScraperConfig(output_dir=tmpdir, output_format="json"))
            s.make_result(ContentType.POST, {"text": "hello"})
            s.make_result(ContentType.POST, {"text": "world"})
            path = s.export()
            assert path.endswith(".json")
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 2
            assert data[0]["data"]["text"] == "hello"

    def test_export_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = DummyScraper(ScraperConfig(output_dir=tmpdir, output_format="jsonl"))
            s.make_result(ContentType.POST, {"text": "a"})
            s.make_result(ContentType.POST, {"text": "b"})
            path = s.export()
            assert path.endswith(".jsonl")
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["data"]["text"] == "a"

    def test_export_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = DummyScraper(ScraperConfig(output_dir=tmpdir, output_format="csv"))
            s.make_result(ContentType.POST, {"text": "hello"})
            path = s.export()
            assert path.endswith(".csv")
            with open(path) as f:
                content = f.read()
            assert "hello" in content

    def test_export_empty(self):
        s = DummyScraper()
        path = s.export()
        assert path == ""


# --- Platform Registry tests ---

class TestRegistry:
    def test_all_platforms_importable(self):
        from config.settings import PLATFORMS, get_scraper_class
        for name in PLATFORMS:
            cls = get_scraper_class(name)
            assert cls is not None
            assert hasattr(cls, "platform_name")
            assert hasattr(cls, "scrape_profile")
            assert hasattr(cls, "scrape_posts")
            assert hasattr(cls, "search")

    def test_unknown_platform_raises(self):
        from config.settings import get_scraper_class
        with pytest.raises(ValueError, match="Unknown platform"):
            get_scraper_class("nonexistent_platform")

    def test_platform_count(self):
        from config.settings import PLATFORMS
        assert len(PLATFORMS) == 20

    def test_all_scrapers_instantiate(self):
        from config.settings import PLATFORMS, get_scraper_class
        for name in PLATFORMS:
            cls = get_scraper_class(name)
            instance = cls()
            assert instance.platform_name == name or instance.platform_name in name
