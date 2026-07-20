"""
Minimal persistent state store. Deliberately just a JSON file behind a lock --
this assignment explicitly says observability "can be simple (e.g., logs,
lightweight metrics)". A real deployment would swap this for Postgres/SQLite
without touching the rest of the app.
"""
import json
import os
import threading
import time

from .settings import STORE_PATH

_LOCK = threading.Lock()
_PATH = STORE_PATH


def _load() -> dict:
    if not os.path.exists(_PATH):
        return {"records": {}}
    with open(_PATH, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _PATH)


def upsert_record(issue_number: int, **fields) -> dict:
    with _LOCK:
        data = _load()
        key = str(issue_number)
        record = data["records"].get(key, {"issue_number": issue_number})
        record.update(fields)
        record["updated_at"] = time.time()
        data["records"][key] = record
        _save(data)
        return record


def get_record(issue_number: int) -> dict | None:
    data = _load()
    return data["records"].get(str(issue_number))


def all_records() -> list[dict]:
    data = _load()
    return sorted(data["records"].values(), key=lambda r: r.get("created_at", 0))


def active_records() -> list[dict]:
    return [r for r in all_records() if r.get("status") not in
            ("finished", "blocked", "expired", "stopped")]


def summary() -> dict:
    records = all_records()
    total = len(records)
    finished = [r for r in records if r.get("status") == "finished"]
    with_pr = [r for r in records if r.get("pr_url")]
    blocked = [r for r in records if r.get("status") in ("blocked", "expired", "stopped")]
    durations = [
        r["updated_at"] - r["created_at"]
        for r in finished
        if r.get("created_at") and r.get("updated_at")
    ]
    avg_time_to_finish_sec = sum(durations) / len(durations) if durations else None
    return {
        "total_triggered": total,
        "finished": len(finished),
        "prs_opened": len(with_pr),
        "blocked_or_failed": len(blocked),
        "in_progress": total - len(finished) - len(blocked),
        "success_rate_pct": round(100 * len(with_pr) / total, 1) if total else None,
        "avg_time_to_finish_sec": round(avg_time_to_finish_sec, 1) if avg_time_to_finish_sec else None,
    }
