"""Tests for the webhook automation layer."""

import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.automation.orchestrator import Orchestrator, categorize
from app.automation.store import Store
from app.automation.webhook import create_router, parse_payload, verify_signature
from app.config import Settings
from app.models import TriggerResult


def _settings(**overrides) -> Settings:
    base = dict(
        api_key="cog_test",
        base_url="https://api.devin.ai",
        request_timeout=5.0,
        org_id="org_test",
        github_repo="asmitakhaneja/superset",
        github_token=None,
        github_webhook_secret="",
        trigger_label="devin-fix",
        poll_interval_sec=30,
        store_path="/tmp/unused.json",
    )
    base.update(overrides)
    return Settings(**base)


# -- signature / payload ----------------------------------------------------
def test_verify_signature_roundtrip() -> None:
    secret = "s3cret"
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(secret, body, good) is True
    assert verify_signature(secret, body, "sha256=deadbeef") is False
    assert verify_signature(secret, body, None) is False
    # No configured secret => verification is skipped.
    assert verify_signature("", body, None) is True


def test_parse_payload_json_and_form() -> None:
    payload = {"action": "labeled", "issue": {"number": 7}}
    raw_json = json.dumps(payload).encode()
    assert parse_payload(raw_json, "application/json") == payload
    form = b"payload=" + json.dumps(payload).encode()
    assert parse_payload(form, "application/x-www-form-urlencoded") == payload


def test_categorize_buckets() -> None:
    assert categorize("Fix XSS in renderer", []) == "security"
    assert categorize("Bump lodash", ["dependencies"]) == "dependency"
    assert categorize("Add test coverage", []) == "tests"
    assert categorize("Tidy up imports", []) == "quality"


# -- store ------------------------------------------------------------------
def test_store_lifecycle(tmp_path) -> None:
    store = Store(str(tmp_path / "state.json"))
    assert store.all() == []
    store.upsert(1, title="A", category="tests", status="running", created_at=100.0)
    store.upsert(2, title="B", category="security", status="finished", created_at=50.0)
    store.upsert(2, pr_url="https://github.com/x/y/pull/2")

    # sorted by created_at ascending
    assert [r.issue_number for r in store.all()] == [2, 1]
    assert store.get(2).pr_url.endswith("/pull/2")
    assert [r.issue_number for r in store.active()] == [1]

    summary = store.summary()
    assert summary.total_triggered == 2
    assert summary.finished == 1
    assert summary.prs_opened == 1
    assert summary.success_rate_pct == 50.0


# -- webhook router ---------------------------------------------------------
class _FakeOrchestrator:
    def __init__(self, store: Store) -> None:
        self._store = store
        self.triggered: list[int] = []

    def trigger(self, store, *, issue_number, title, body, labels) -> TriggerResult:
        self.triggered.append(issue_number)
        record = store.upsert(
            issue_number,
            title=title,
            category="tests",
            session_id=f"devin-{issue_number}",
            status="running",
            created_at=1.0,
        )
        return TriggerResult(skipped=False, record=record)

    def close(self) -> None:
        pass


def _client(store: Store, orchestrator: _FakeOrchestrator, **settings_kw):
    app = FastAPI()
    app.include_router(
        create_router(_settings(**settings_kw), store, lambda: orchestrator),
        prefix="/api",
    )
    return TestClient(app)


def test_webhook_triggers_on_label(tmp_path) -> None:
    store = Store(str(tmp_path / "s.json"))
    orch = _FakeOrchestrator(store)
    client = _client(store, orch)
    payload = {
        "action": "labeled",
        "issue": {
            "number": 42,
            "title": "Broken thing",
            "body": "details",
            "labels": [{"name": "devin-fix"}],
        },
    }
    resp = client.post(
        "/api/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["skipped"] is False
    assert orch.triggered == [42]
    assert store.get(42) is not None


def test_webhook_skips_without_label(tmp_path) -> None:
    store = Store(str(tmp_path / "s.json"))
    orch = _FakeOrchestrator(store)
    client = _client(store, orch)
    payload = {
        "action": "labeled",
        "issue": {"number": 43, "title": "x", "labels": [{"name": "bug"}]},
    }
    resp = client.post(
        "/api/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["skipped"] is True
    assert "missing label" in resp.json()["reason"]
    assert orch.triggered == []


def test_webhook_rejects_bad_signature(tmp_path) -> None:
    store = Store(str(tmp_path / "s.json"))
    orch = _FakeOrchestrator(store)
    client = _client(store, orch, github_webhook_secret="topsecret")
    resp = client.post(
        "/api/webhook/github",
        json={"action": "labeled", "issue": {"number": 1}},
        headers={"X-Hub-Signature-256": "sha256=nope"},
    )
    assert resp.status_code == 401


def test_poll_once_updates_status(tmp_path, monkeypatch) -> None:
    store = Store(str(tmp_path / "s.json"))
    store.upsert(9, session_id="devin-9", status="running", created_at=1.0)
    orch = Orchestrator(_settings())
    monkeypatch.setattr(
        orch,
        "get_session",
        lambda sid: {
            "status": "finished",
            "pull_request": {"url": "https://github.com/x/y/pull/9"},
        },
    )
    orch.poll_once(store)
    orch.close()
    record = store.get(9)
    assert record.status == "finished"
    assert record.pr_url.endswith("/pull/9")
