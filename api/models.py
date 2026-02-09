"""SQLAlchemy ORM models."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from api.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # profile, posts, search
    target = Column(String(500), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, index=True)
    max_results = Column(Integer, default=100)
    config = Column(JSON, default=dict)  # proxy, delay, headless, etc.
    result_count = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.utcnow(), index=True
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    results = relationship(
        "ScrapeResult", back_populates="job", cascade="all, delete-orphan"
    )


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("scrape_jobs.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    content_type = Column(String(30), nullable=False, index=True)
    data = Column(JSON, nullable=False)
    url = Column(String(2000), nullable=True)
    scraped_at = Column(
        DateTime, default=lambda: datetime.utcnow(), index=True
    )

    job = relationship("ScrapeJob", back_populates="results")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    platform = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    target = Column(String(500), nullable=False)
    max_results = Column(Integer, default=100)
    config = Column(JSON, default=dict)
    cron_expression = Column(String(100), nullable=False)  # e.g. "0 */6 * * *"
    enabled = Column(Integer, default=1)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
