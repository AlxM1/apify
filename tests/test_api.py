"""Tests for the FastAPI backend."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.database import Base, engine
from api.main import app


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    asyncio.get_event_loop().run_until_complete(_create())
    yield
    asyncio.get_event_loop().run_until_complete(_drop())


async def _create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client():
    return TestClient(app)


# ── Dashboard ────────────────────────────────────────────


class TestDashboard:
    def test_empty_dashboard(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_jobs"] == 0
        assert data["total_results"] == 0
        assert data["running_jobs"] == 0


# ── Platforms ────────────────────────────────────────────


class TestPlatforms:
    def test_list_platforms(self, client):
        resp = client.get("/api/platforms")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 20
        names = [p["name"] for p in data]
        assert "reddit" in names
        assert "youtube" in names
        assert "twitter" in names

    def test_get_platform(self, client):
        resp = client.get("/api/platforms/reddit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "reddit"
        assert "actions" in data

    def test_unknown_platform(self, client):
        resp = client.get("/api/platforms/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


# ── Scrapes ──────────────────────────────────────────────


class TestScrapes:
    def test_create_scrape(self, client):
        # Mock the launch_job to avoid actually running
        with patch("api.routes.scrapes.launch_job"):
            resp = client.post(
                "/api/scrapes",
                json={
                    "platform": "reddit",
                    "action": "posts",
                    "target": "r/python",
                    "max_results": 10,
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["platform"] == "reddit"
        assert data["action"] == "posts"
        assert data["target"] == "r/python"
        assert data["status"] == "pending"
        assert data["id"] >= 1

    def test_create_scrape_invalid_platform(self, client):
        resp = client.post(
            "/api/scrapes",
            json={
                "platform": "fakebook",
                "action": "posts",
                "target": "test",
            },
        )
        assert resp.status_code == 400

    def test_create_scrape_invalid_action(self, client):
        resp = client.post(
            "/api/scrapes",
            json={
                "platform": "reddit",
                "action": "hack",
                "target": "test",
            },
        )
        assert resp.status_code == 422

    def test_list_scrapes(self, client):
        with patch("api.routes.scrapes.launch_job"):
            client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
            client.post(
                "/api/scrapes",
                json={"platform": "youtube", "action": "search", "target": "python"},
            )
        resp = client.get("/api/scrapes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_get_scrape(self, client):
        with patch("api.routes.scrapes.launch_job"):
            create = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        job_id = create.json()["id"]
        resp = client.get(f"/api/scrapes/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == job_id
        assert "results" in data

    def test_get_nonexistent(self, client):
        resp = client.get("/api/scrapes/99999")
        assert resp.status_code == 404

    def test_delete_scrape(self, client):
        with patch("api.routes.scrapes.launch_job"):
            create = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        job_id = create.json()["id"]
        resp = client.delete(f"/api/scrapes/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        resp = client.get(f"/api/scrapes/{job_id}")
        assert resp.status_code == 404

    def test_retry_scrape(self, client):
        with patch("api.routes.scrapes.launch_job"):
            create = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        job_id = create.json()["id"]
        with patch("api.routes.scrapes.launch_job"):
            resp = client.post(f"/api/scrapes/{job_id}/retry")
        assert resp.status_code == 201
        new_job = resp.json()
        assert new_job["id"] != job_id
        assert new_job["platform"] == "reddit"

    def test_filter_by_platform(self, client):
        with patch("api.routes.scrapes.launch_job"):
            client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
            client.post(
                "/api/scrapes",
                json={"platform": "youtube", "action": "search", "target": "test"},
            )
        resp = client.get("/api/scrapes?platform=reddit")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["platform"] == "reddit"


# ── Results ──────────────────────────────────────────────


class TestResults:
    def test_empty_results(self, client):
        resp = client.get("/api/results")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_result_stats(self, client):
        resp = client.get("/api/results/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0

    def test_export_empty_json(self, client):
        resp = client.get("/api/results/export?format=json")
        assert resp.status_code == 200


# ── Dashboard after data ─────────────────────────────────


class TestDashboardWithData:
    def test_dashboard_counts_jobs(self, client):
        with patch("api.routes.scrapes.launch_job"):
            client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
            client.post(
                "/api/scrapes",
                json={"platform": "youtube", "action": "search", "target": "test"},
            )
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_jobs"] == 2
        assert data["platforms_used"] == 2
