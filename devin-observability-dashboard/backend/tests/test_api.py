"""Smoke tests for the dashboard API (demo mode)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_demo_mode() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_overview_returns_consistent_kpis() -> None:
    data = client.get("/api/overview?days=30").json()
    assert data["is_demo"] is True
    assert data["kpis"]["total_sessions"] > 0
    assert len(data["timeseries"]) == 30
    # merge rate is a valid fraction
    assert 0.0 <= data["kpis"]["pr_merge_rate"] <= 1.0
    # every timeseries point covers all four products
    for point in data["timeseries"]:
        assert "acus_devin" in point
        assert point["sessions"] >= 0


def test_session_messages_drilldown() -> None:
    overview = client.get("/api/overview?days=30").json()
    session_id = overview["recent_sessions"][0]["session_id"]
    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert len(body["items"]) > 0
    assert body["items"][0]["source"] in {"user", "devin"}


def test_unknown_session_returns_404() -> None:
    resp = client.get("/api/sessions/devin-does-not-exist/messages")
    assert resp.status_code == 404
