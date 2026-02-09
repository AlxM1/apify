"""Tests for production features: auth, scheduler, bulk, webhooks, retention."""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from api.database import Base, engine
from api.main import app


@pytest.fixture(autouse=True)
def setup_db():
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


# ── Auth ─────────────────────────────────────────────────


class TestAuth:
    def test_auth_status_disabled(self, client):
        """When API_KEY is empty, auth is disabled."""
        resp = client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_enabled"] is False

    def test_create_scrape_without_auth(self, client):
        """When auth is disabled, scrapes work without credentials."""
        with patch("api.routes.scrapes.launch_job"):
            resp = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        assert resp.status_code == 201

    def test_auth_enforced_when_configured(self, client):
        """When API_KEY is set, requests without key should fail."""
        with patch("api.config.settings.api_key", "test-secret-key"):
            resp = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
            assert resp.status_code == 401

    def test_auth_with_api_key(self, client):
        """Requests with valid API key should succeed."""
        with patch("api.config.settings.api_key", "test-secret-key"):
            with patch("api.routes.scrapes.launch_job"):
                resp = client.post(
                    "/api/scrapes",
                    json={"platform": "reddit", "action": "posts", "target": "r/test"},
                    headers={"X-API-Key": "test-secret-key"},
                )
            assert resp.status_code == 201

    def test_auth_wrong_key_rejected(self, client):
        """Requests with wrong API key should be rejected."""
        with patch("api.config.settings.api_key", "test-secret-key"):
            resp = client.post(
                "/api/scrapes",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

    def test_jwt_token_flow(self):
        """JWT tokens should be creatable and verifiable."""
        from api.auth import create_access_token, verify_jwt

        token = create_access_token({"sub": "testuser", "role": "admin"})
        assert isinstance(token, str)
        assert token.count(".") == 2

        payload = verify_jwt(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert "exp" in payload


# ── Scheduler ────────────────────────────────────────────


class TestScheduler:
    def test_compute_next_run(self):
        from api.scheduler import compute_next_run

        base = datetime(2026, 1, 1, 0, 0, 0)
        nxt = compute_next_run("0 */6 * * *", base)
        assert nxt == datetime(2026, 1, 1, 6, 0, 0)

    def test_compute_next_run_daily(self):
        from api.scheduler import compute_next_run

        base = datetime(2026, 1, 1, 12, 0, 0)
        nxt = compute_next_run("0 0 * * *", base)
        assert nxt == datetime(2026, 1, 2, 0, 0, 0)

    def test_create_schedule(self, client):
        resp = client.post(
            "/api/schedules",
            json={
                "name": "Test Schedule",
                "platform": "reddit",
                "action": "posts",
                "target": "r/python",
                "cron_expression": "0 */12 * * *",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Schedule"
        assert data["enabled"] is True
        assert data["next_run"] is not None

    def test_list_schedules(self, client):
        client.post(
            "/api/schedules",
            json={
                "name": "S1",
                "platform": "reddit",
                "action": "posts",
                "target": "r/test",
                "cron_expression": "0 * * * *",
            },
        )
        resp = client.get("/api/schedules")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_toggle_schedule(self, client):
        create = client.post(
            "/api/schedules",
            json={
                "name": "Toggle Test",
                "platform": "reddit",
                "action": "posts",
                "target": "r/test",
                "cron_expression": "0 * * * *",
            },
        )
        sid = create.json()["id"]

        # Disable
        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # Re-enable
        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": True})
        assert resp.json()["enabled"] is True

    def test_delete_schedule(self, client):
        create = client.post(
            "/api/schedules",
            json={
                "name": "Del Test",
                "platform": "reddit",
                "action": "posts",
                "target": "r/test",
                "cron_expression": "0 * * * *",
            },
        )
        sid = create.json()["id"]
        resp = client.delete(f"/api/schedules/{sid}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_cron(self, client):
        resp = client.post(
            "/api/schedules",
            json={
                "name": "Bad Cron",
                "platform": "reddit",
                "action": "posts",
                "target": "r/test",
                "cron_expression": "not a cron",
            },
        )
        assert resp.status_code == 400


# ── Bulk ─────────────────────────────────────────────────


class TestBulk:
    def test_bulk_scrape(self, client):
        with patch("api.routes.bulk.launch_job"):
            resp = client.post(
                "/api/bulk/scrape",
                json={
                    "targets": [
                        {"platform": "reddit", "action": "posts", "target": "r/python"},
                        {"platform": "youtube", "action": "search", "target": "python tutorial"},
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["launched"] == 2
        assert len(data["job_ids"]) == 2

    def test_bulk_scrape_invalid_platform(self, client):
        with patch("api.routes.bulk.launch_job"):
            resp = client.post(
                "/api/bulk/scrape",
                json={
                    "targets": [
                        {"platform": "reddit", "target": "r/python"},
                        {"platform": "fakebook", "target": "test"},
                    ]
                },
            )
        data = resp.json()
        assert data["launched"] == 1
        assert len(data["errors"]) == 1

    def test_deduplicate_dry_run(self, client):
        resp = client.post("/api/bulk/deduplicate?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["total_duplicates"] == 0


# ── Webhooks ─────────────────────────────────────────────


class TestWebhooks:
    def test_webhook_trigger_scrape(self, client):
        with patch("api.routes.webhooks.launch_job"):
            resp = client.post(
                "/api/webhooks/scrape",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        assert resp.status_code == 201

    def test_n8n_trigger(self, client):
        with patch("api.routes.webhooks.launch_job"):
            resp = client.post(
                "/api/webhooks/n8n/trigger",
                json={"platform": "reddit", "action": "posts", "target": "r/test"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert "job_id" in data

    def test_n8n_trigger_missing_fields(self, client):
        resp = client.post(
            "/api/webhooks/n8n/trigger",
            json={"platform": "reddit"},
        )
        assert resp.status_code == 400


# ── Config ───────────────────────────────────────────────


class TestConfig:
    def test_settings_defaults(self):
        from api.config import settings

        assert settings.port == 8000
        assert settings.default_max_results == 100
        assert settings.scheduler_enabled is True
        assert settings.rate_limit == "60/minute"

    def test_settings_auth_disabled_by_default(self):
        from api.config import settings

        assert settings.api_key == ""


# ── WebSocket ────────────────────────────────────────────


class TestWebSocket:
    def test_ws_manager_broadcast(self):
        from api.ws import ConnectionManager

        mgr = ConnectionManager()
        assert len(mgr.active) == 0

    def test_ws_endpoint_exists(self, client):
        # WebSocket route should be registered
        ws_routes = [
            r for r in app.routes
            if hasattr(r, 'path') and r.path == '/ws'
        ]
        assert len(ws_routes) == 1
