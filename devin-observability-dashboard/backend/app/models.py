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


class AutomationRecord(BaseModel):
    """A single GitHub issue that was routed to a Devin session."""

    issue_number: int
    title: str | None = None
    category: str | None = None
    status: str = "unknown"
    session_id: str | None = None
    session_url: str | None = None
    pr_url: str | None = None
    created_at: float | None = None
    updated_at: float | None = None


class AutomationSummary(BaseModel):
    total_triggered: int = 0
    in_progress: int = 0
    finished: int = 0
    prs_opened: int = 0
    blocked_or_failed: int = 0
    success_rate_pct: float | None = None
    avg_time_to_finish_sec: float | None = None


class AutomationStatus(BaseModel):
    """Real-time view of webhook-triggered remediation sessions."""

    enabled: bool
    is_demo: bool
    repo: str
    trigger_label: str
    generated_at: int
    summary: AutomationSummary
    records: list[AutomationRecord]


class TriggerResult(BaseModel):
    skipped: bool
    reason: str | None = None
    record: AutomationRecord | None = None
