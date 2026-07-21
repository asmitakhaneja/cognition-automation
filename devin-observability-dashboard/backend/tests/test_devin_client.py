"""Tests that the dashboard client uses organization-scoped v3 endpoints."""

import httpx
import pytest

from app.config import Settings
from app.devin_client import DevinClient, _to_epoch


def _settings(org_id: str | None = "org-abc") -> Settings:
    return Settings(
        api_key="cog_test",
        base_url="https://api.devin.ai",
        request_timeout=5.0,
        org_id=org_id,
        github_repo="asmitakhaneja/superset",
        github_token=None,
        github_webhook_secret="",
        trigger_label="devin-fix",
        poll_interval_sec=30,
        store_path="/tmp/unused.json",
    )


def _client_with_capture(handler) -> tuple[DevinClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = DevinClient(_settings())
    client._client = httpx.Client(
        base_url="https://api.devin.ai",
        transport=httpx.MockTransport(_record),
    )
    return client, requests


def test_requires_org_id() -> None:
    with pytest.raises(ValueError):
        DevinClient(_settings(org_id=None))


def test_list_sessions_hits_org_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "session_id": "devin-1",
                        "status": "exit",
                        "created_at": 1700000000,
                        "acus_consumed": 3,
                        "pull_requests": [],
                    }
                ],
                "has_next_page": False,
            },
        )

    client, requests = _client_with_capture(handler)
    sessions = client.list_sessions(created_after=0)
    client.close()
    assert requests[0].url.path == "/v3/organizations/org-abc/sessions"
    assert len(sessions) == 1


def test_consumption_and_messages_hit_org_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "consumption" in request.url.path:
            return httpx.Response(200, json={"consumption_by_date": [{"date": 1}]})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "event_id": "e1",
                        "source": "devin",
                        "message": "hi",
                        "created_at": "2023-11-14T22:13:20Z",
                    }
                ],
                "has_next_page": False,
            },
        )

    client, requests = _client_with_capture(handler)
    client.daily_consumption(0, 1)
    msgs = client.session_messages("devin-1")
    client.close()
    paths = [r.url.path for r in requests]
    assert "/v3/organizations/org-abc/consumption/daily" in paths
    assert "/v3/organizations/org-abc/sessions/devin-1/messages" in paths
    # ISO timestamp parsed to epoch seconds.
    assert msgs[0].created_at == 1700000000


def test_to_epoch_variants() -> None:
    assert _to_epoch(1700000000) == 1700000000
    assert _to_epoch("1700000000") == 1700000000
    assert _to_epoch("2023-11-14T22:13:20Z") == 1700000000
    assert _to_epoch(None) == 0
    assert _to_epoch("not-a-date") == 0
