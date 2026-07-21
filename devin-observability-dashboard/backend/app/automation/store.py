"""Persistent state for webhook-triggered remediation sessions.

Deliberately a single JSON file behind a lock: the point of this store is to
give the dashboard a real-time, restart-surviving view of automation activity
without standing up a database. Swap in Postgres/SQLite for production without
touching the rest of the app.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

from ..models import AutomationRecord, AutomationSummary

logger = logging.getLogger("automation.store")

# Session statuses we treat as terminal (poller stops watching them).
TERMINAL_STATUSES = {"finished", "blocked", "expired", "stopped"}
FAILED_STATUSES = {"blocked", "expired", "stopped"}


class Store:
    """Thread-safe JSON-file store keyed by GitHub issue number."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _read_raw(self) -> dict[str, dict]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.error("Failed to load store from %s", self._path, exc_info=True)
            return {}
        records = data.get("records", {})
        return records if isinstance(records, dict) else {}

    def _write_raw(self, records: dict[str, dict]) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"records": records}, fh, indent=2)
        os.replace(tmp, self._path)

    def upsert(
        self,
        issue_number: int,
        *,
        title: str | None = None,
        category: str | None = None,
        status: str | None = None,
        session_id: str | None = None,
        session_url: str | None = None,
        pr_url: str | None = None,
        created_at: float | None = None,
    ) -> AutomationRecord:
        with self._lock:
            records = self._read_raw()
            key = str(issue_number)
            record = records.get(key, {"issue_number": issue_number})
            updates = {
                "title": title,
                "category": category,
                "status": status,
                "session_id": session_id,
                "session_url": session_url,
                "pr_url": pr_url,
                "created_at": created_at,
            }
            for field, value in updates.items():
                if value is not None:
                    record[field] = value
            record["updated_at"] = time.time()
            records[key] = record
            self._write_raw(records)
            logger.info(
                "Stored issue #%d (status=%s)", issue_number, record.get("status")
            )
            return AutomationRecord.model_validate(record)

    def get(self, issue_number: int) -> AutomationRecord | None:
        raw = self._read_raw().get(str(issue_number))
        return AutomationRecord.model_validate(raw) if raw else None

    def all(self) -> list[AutomationRecord]:
        records = self._read_raw().values()
        parsed = [AutomationRecord.model_validate(r) for r in records]
        return sorted(parsed, key=lambda r: r.created_at or 0.0)

    def active(self) -> list[AutomationRecord]:
        return [r for r in self.all() if r.status not in TERMINAL_STATUSES]

    def replace_all(self, records: list[AutomationRecord]) -> None:
        """Overwrite the store — used to seed demo data."""
        with self._lock:
            payload = {
                str(r.issue_number): r.model_dump(exclude_none=True) for r in records
            }
            self._write_raw(payload)

    def summary(self) -> AutomationSummary:
        records = self.all()
        total = len(records)
        finished = [r for r in records if r.status == "finished"]
        with_pr = [r for r in records if r.pr_url]
        blocked = [r for r in records if r.status in FAILED_STATUSES]
        durations = [
            r.updated_at - r.created_at
            for r in finished
            if r.created_at and r.updated_at
        ]
        avg = sum(durations) / len(durations) if durations else None
        return AutomationSummary(
            total_triggered=total,
            finished=len(finished),
            prs_opened=len(with_pr),
            blocked_or_failed=len(blocked),
            in_progress=total - len(finished) - len(blocked),
            success_rate_pct=(round(100 * len(with_pr) / total, 1) if total else None),
            avg_time_to_finish_sec=round(avg, 1) if avg else None,
        )
