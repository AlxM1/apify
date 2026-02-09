"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Requests ──────────────────────────────────────────────────


class ScrapeRequest(BaseModel):
    platform: str
    action: str = Field(pattern="^(profile|posts|search)$")
    target: str
    max_results: int = Field(default=100, ge=1, le=10000)
    proxy: str | None = None
    delay: float = Field(default=1.0, ge=0)
    headless: bool = True


class ScheduleRequest(BaseModel):
    name: str
    platform: str
    action: str = Field(pattern="^(profile|posts|search)$")
    target: str
    max_results: int = 100
    cron_expression: str = "0 */6 * * *"
    config: dict[str, Any] = Field(default_factory=dict)


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_results: int | None = None
    config: dict[str, Any] | None = None


# ── Responses ─────────────────────────────────────────────────


class PlatformInfo(BaseModel):
    name: str
    module: str
    rate_limit: float


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    action: str
    target: str
    status: str
    max_results: int
    result_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None


class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    platform: str
    content_type: str
    data: dict[str, Any]
    url: str | None
    scraped_at: datetime


class JobDetailResponse(JobResponse):
    results: list[ResultResponse] = []


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str
    action: str
    target: str
    max_results: int
    cron_expression: str
    enabled: bool
    last_run: datetime | None
    next_run: datetime | None
    created_at: datetime


class StatsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    running_jobs: int
    total_results: int
    platforms_used: list[str]
    recent_jobs: list[JobResponse]


class DashboardStats(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    running_jobs: int
    pending_jobs: int
    total_results: int
    results_today: int
    platforms_used: int
    avg_duration: float | None
