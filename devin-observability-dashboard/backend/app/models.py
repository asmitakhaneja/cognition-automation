"""Pydantic response models shared by every dashboard API endpoint.

These are the *normalized* shapes the frontend consumes. They are deliberately
decoupled from the raw Devin API payloads so that the aggregation layer can
absorb schema differences between API versions.
"""
from __future__ import annotations

from pydantic import BaseModel


class PullRequest(BaseModel):
    url: str
    state: str | None = None


class Session(BaseModel):
    session_id: str
    title: str | None = None
    status: str
    created_at: int  # unix seconds
    updated_at: int  # unix seconds
    acus_consumed: float
    org_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    origin: str | None = None
    category: str | None = None
    repo: str | None = None
    tags: list[str] = []
    pull_requests: list[PullRequest] = []


class Kpis(BaseModel):
    total_sessions: int
    total_acus: float
    prs_created: int
    prs_merged: int
    pr_merge_rate: float  # 0..1
    success_rate: float  # finished / total, 0..1
    active_users: int
    acus_per_merged_pr: float
    avg_acus_per_session: float


class TimePoint(BaseModel):
    date: str  # ISO date (YYYY-MM-DD)
    sessions: int = 0
    prs_merged: int = 0
    acus: float = 0.0
    acus_devin: float = 0.0
    acus_cascade: float = 0.0
    acus_terminal: float = 0.0
    acus_review: float = 0.0


class NamedCount(BaseModel):
    name: str
    count: int = 0
    acus: float = 0.0


class Overview(BaseModel):
    generated_at: int
    is_demo: bool
    range_days: int
    kpis: Kpis
    timeseries: list[TimePoint]
    by_status: list[NamedCount]
    by_category: list[NamedCount]
    by_origin: list[NamedCount]
    by_repo: list[NamedCount]
    by_user: list[NamedCount]
    by_org: list[NamedCount]
    recent_sessions: list[Session]


class Message(BaseModel):
    event_id: str
    source: str  # "devin" | "user"
    message: str
    created_at: int


class MessagesResponse(BaseModel):
    session_id: str
    is_demo: bool
    items: list[Message]
