"""Deterministic, realistic demo dataset.

Used whenever no Devin credential is configured so the dashboard is fully
functional out of the box (and so the UI can be developed without hitting the
live API). The data is generated with a fixed seed so the dashboard looks the
same on every load.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from .models import Message, PullRequest, Session

_SEED = 20240721
_DAYS = 30

_USERS = [
    ("user-a1", "Asmita Khaneja"),
    ("user-b2", "Marcus Lee"),
    ("user-c3", "Priya Nair"),
    ("user-d4", "Diego Alvarez"),
    ("user-e5", "Sam Okafor"),
    ("user-f6", "Yuki Tanaka"),
    ("user-g7", "Elena Rossi"),
    ("user-h8", "Tom Becker"),
]

_ORGS = [
    ("org-platform", "Platform"),
    ("org-payments", "Payments"),
    ("org-data", "Data"),
]

_REPOS = [
    "acme/superset",
    "acme/payments-api",
    "acme/web-app",
    "acme/data-pipeline",
    "acme/infra",
    "acme/mobile",
]

_CATEGORIES = [
    "bug_fixing",
    "feature_development",
    "code_review_and_analysis",
    "unit_test_generation",
    "refactoring_and_optimization",
    "ci_cd_and_devops",
    "documentation_and_content",
    "migrations_and_upgrades",
    "production_investigation",
    "research_and_exploration",
]

_ORIGINS = ["webapp", "slack", "api", "linear", "jira", "cli", "automation"]

# Weighted status distribution -> mostly successful ("exit"), some in-flight.
_STATUS_WEIGHTS = [
    ("exit", 62),
    ("running", 10),
    ("suspended", 12),
    ("error", 8),
    ("new", 4),
    ("claimed", 4),
]

_TITLES = [
    "Fix flaky auth integration test",
    "Add retry with backoff to webhook dispatcher",
    "Upgrade Superset to 4.x and fix deprecations",
    "Investigate elevated 5xx on checkout endpoint",
    "Generate unit tests for pricing module",
    "Refactor dashboard query caching layer",
    "Add pagination to sessions list API",
    "Document deployment runbook",
    "Migrate CI from CircleCI to GitHub Actions",
    "Reduce Docker image size for web-app",
    "Fix N+1 query in reports view",
    "Add feature flag for new onboarding flow",
    "Patch CVE in transitive dependency",
    "Wire up Datadog tracing to payments-api",
    "Backfill missing analytics events",
]


def _weighted_choice(rng: random.Random, weighted: list[tuple[str, int]]) -> str:
    total = sum(w for _, w in weighted)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, weight in weighted:
        upto += weight
        if r <= upto:
            return value
    return weighted[-1][0]


def _day_activity(rng: random.Random, day_index: int) -> int:
    """Sessions per day: weekday-heavy with a gentle upward adoption trend."""
    base = 6 + int(day_index * 0.35)  # adoption ramp
    # dampen weekends
    weekday = (day_index) % 7
    if weekday in (5, 6):
        base = int(base * 0.4)
    jitter = rng.randint(-2, 3)
    return max(1, base + jitter)


def generate_sessions() -> list[Session]:
    rng = random.Random(_SEED)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    sessions: list[Session] = []
    counter = 0
    for day_index in range(_DAYS):
        day = start + timedelta(days=day_index)
        for _ in range(_day_activity(rng, day_index)):
            counter += 1
            user_id, user_name = rng.choice(_USERS)
            org_id, _org_name = rng.choice(_ORGS)
            status = _weighted_choice(rng, _STATUS_WEIGHTS)
            category = rng.choice(_CATEGORIES)
            origin = _weighted_choice(
                rng,
                [
                    ("webapp", 34),
                    ("slack", 24),
                    ("api", 16),
                    ("linear", 9),
                    ("jira", 7),
                    ("cli", 6),
                    ("automation", 4),
                ],
            )
            repo = rng.choice(_REPOS)

            created = day + timedelta(
                hours=rng.randint(7, 20), minutes=rng.randint(0, 59)
            )
            duration_min = rng.randint(4, 220)
            updated = created + timedelta(minutes=duration_min)

            # ACU cost roughly scales with duration + noise.
            acus = round(max(0.05, duration_min / 30.0 * rng.uniform(0.6, 1.5)), 2)

            # PRs: successful sessions usually produce a PR; most get merged.
            prs: list[PullRequest] = []
            if status in {"exit", "suspended"} and rng.random() < 0.72:
                pr_number = 1000 + counter
                merged = rng.random() < 0.78
                state = "merged" if merged else rng.choice(["open", "closed"])
                prs.append(
                    PullRequest(
                        url=f"https://github.com/{repo}/pull/{pr_number}", state=state
                    )
                )

            title = rng.choice(_TITLES)
            sid = (
                "devin-" + hashlib.sha1(f"{_SEED}-{counter}".encode()).hexdigest()[:24]
            )

            sessions.append(
                Session(
                    session_id=sid,
                    title=title,
                    status=status,
                    created_at=int(created.timestamp()),
                    updated_at=int(updated.timestamp()),
                    acus_consumed=acus,
                    org_id=org_id,
                    user_id=user_id,
                    user_name=user_name,
                    origin=origin,
                    category=category,
                    repo=repo,
                    tags=[category],
                    pull_requests=prs,
                )
            )

    sessions.sort(key=lambda s: s.created_at, reverse=True)
    return sessions


def org_display_name(org_id: str | None) -> str:
    for oid, name in _ORGS:
        if oid == org_id:
            return name
    return org_id or "Unknown"


def generate_messages(session: Session) -> list[Message]:
    rng = random.Random(
        int(hashlib.sha1(session.session_id.encode()).hexdigest(), 16) % (2**32)
    )
    base = session.created_at
    items: list[Message] = []

    def add(source: str, text: str, offset: int) -> None:
        items.append(
            Message(
                event_id=hashlib.sha1(
                    f"{session.session_id}-{len(items)}".encode()
                ).hexdigest()[:16],
                source=source,
                message=text,
                created_at=base + offset,
            )
        )

    add("user", session.title or "Please work on this task.", 0)
    add("devin", "Understood. Cloning the repo and inspecting the failing test.", 60)
    add(
        "devin",
        "Reproduced locally. Root cause is a race in the setup fixture.",
        240 + rng.randint(0, 120),
    )
    add(
        "devin",
        "Applied a fix and re-ran the suite — all green. Running lint and typecheck.",
        900 + rng.randint(0, 300),
    )
    if session.pull_requests:
        add(
            "devin",
            f"Opened a PR: {session.pull_requests[0].url}",
            1200 + rng.randint(0, 300),
        )
    if session.status == "error":
        add("devin", "Hit an environment error I could not resolve; escalating.", 1500)
    elif session.status in {"running", "claimed", "new"}:
        add("devin", "Still working through the remaining edge cases.", 1500)
    else:
        add(
            "devin",
            "Task complete. Summary and diff are in the PR description.",
            1500 + rng.randint(0, 200),
        )
    return items
