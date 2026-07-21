"""Turn raw session/consumption data into the normalized dashboard payload.

All heavy lifting (grouping, rate calculations, time bucketing) happens here so
the frontend only ever renders pre-computed numbers.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .models import Kpis, NamedCount, Overview, Session, TimePoint

# A session counts as "successful" when it finished cleanly.
_SUCCESS_STATUSES = {"exit"}
# Synthetic product split used only when the consumption endpoint is unavailable.
_PRODUCT_SPLIT = {"devin": 0.70, "cascade": 0.18, "terminal": 0.07, "review": 0.05}


def _utc_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _session_merged_prs(session: Session) -> int:
    return sum(
        1 for pr in session.pull_requests if (pr.state or "").lower() == "merged"
    )


def _pretty_category(name: str) -> str:
    return name.replace("_", " ").title()


def build_overview(
    sessions: list[Session],
    range_days: int,
    is_demo: bool,
    consumption_by_date: list[dict[str, Any]] | None = None,
    user_names: dict[str, str] | None = None,
) -> Overview:
    user_names = user_names or {}
    for s in sessions:
        if not s.user_name and s.user_id:
            s.user_name = user_names.get(s.user_id, s.user_id[:12])

    total_sessions = len(sessions)
    total_acus = round(sum(s.acus_consumed for s in sessions), 2)
    prs_created = sum(len(s.pull_requests) for s in sessions)
    prs_merged = sum(_session_merged_prs(s) for s in sessions)
    successful = sum(1 for s in sessions if s.status in _SUCCESS_STATUSES)
    active_users = len({s.user_id for s in sessions if s.user_id})

    kpis = Kpis(
        total_sessions=total_sessions,
        total_acus=total_acus,
        prs_created=prs_created,
        prs_merged=prs_merged,
        pr_merge_rate=round(prs_merged / prs_created, 4) if prs_created else 0.0,
        success_rate=round(successful / total_sessions, 4) if total_sessions else 0.0,
        active_users=active_users,
        acus_per_merged_pr=round(total_acus / prs_merged, 2) if prs_merged else 0.0,
        avg_acus_per_session=(
            round(total_acus / total_sessions, 2) if total_sessions else 0.0
        ),
    )

    timeseries = _build_timeseries(sessions, range_days, consumption_by_date)

    return Overview(
        generated_at=int(time.time()),
        is_demo=is_demo,
        range_days=range_days,
        kpis=kpis,
        timeseries=timeseries,
        by_status=_count_by(sessions, key=lambda s: s.status),
        by_category=_count_by(
            sessions, key=lambda s: _pretty_category(s.category or "uncategorized")
        ),
        by_origin=_count_by(sessions, key=lambda s: s.origin or "unknown"),
        by_repo=_count_by(sessions, key=lambda s: s.repo or "unknown", limit=10),
        by_user=_count_by(
            sessions, key=lambda s: s.user_name or s.user_id or "unknown", limit=10
        ),
        by_org=_count_by(sessions, key=lambda s: s.org_id or "unknown", limit=10),
        recent_sessions=sessions[:60],
    )


def _count_by(
    sessions: Iterable[Session],
    key,
    limit: int | None = None,
) -> list[NamedCount]:
    counts: dict[str, int] = defaultdict(int)
    acus: dict[str, float] = defaultdict(float)
    for s in sessions:
        k = key(s)
        counts[k] += 1
        acus[k] += s.acus_consumed
    result = [
        NamedCount(name=name, count=counts[name], acus=round(acus[name], 2))
        for name in counts
    ]
    result.sort(key=lambda nc: nc.count, reverse=True)
    if limit is not None:
        result = result[:limit]
    return result


def _build_timeseries(
    sessions: list[Session],
    range_days: int,
    consumption_by_date: list[dict[str, Any]] | None,
) -> list[TimePoint]:
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(range_days - 1, -1, -1)]
    points: dict[str, TimePoint] = {
        d.strftime("%Y-%m-%d"): TimePoint(date=d.strftime("%Y-%m-%d")) for d in days
    }

    for s in sessions:
        d = _utc_date(s.created_at)
        tp = points.get(d)
        if tp is None:
            continue
        tp.sessions += 1
        tp.prs_merged += _session_merged_prs(s)
        tp.acus = round(tp.acus + s.acus_consumed, 2)

    # Product breakdown: real consumption data if available, else synthesized.
    consumption_map: dict[str, dict[str, float]] = {}
    if consumption_by_date:
        for entry in consumption_by_date:
            date_ts = entry.get("date")
            if date_ts is None:
                continue
            d = _utc_date(int(date_ts))
            by_product = entry.get("acus_by_product", {}) or {}
            consumption_map[d] = {
                "devin": float(by_product.get("devin", 0) or 0),
                "cascade": float(by_product.get("cascade", 0) or 0),
                "terminal": float(by_product.get("terminal", 0) or 0),
                "review": float(by_product.get("review", 0) or 0),
            }

    for d, tp in points.items():
        if d in consumption_map:
            cm = consumption_map[d]
            tp.acus_devin = round(cm["devin"], 2)
            tp.acus_cascade = round(cm["cascade"], 2)
            tp.acus_terminal = round(cm["terminal"], 2)
            tp.acus_review = round(cm["review"], 2)
            # Prefer authoritative consumption total when present.
            tp.acus = round(sum(cm.values()), 2)
        else:
            tp.acus_devin = round(tp.acus * _PRODUCT_SPLIT["devin"], 2)
            tp.acus_cascade = round(tp.acus * _PRODUCT_SPLIT["cascade"], 2)
            tp.acus_terminal = round(tp.acus * _PRODUCT_SPLIT["terminal"], 2)
            tp.acus_review = round(tp.acus * _PRODUCT_SPLIT["review"], 2)

    return [points[d.strftime("%Y-%m-%d")] for d in days]
