"""Thin client around the Devin organization API (v3).

All reads are scoped to a single organization via the
``/v3/organizations/{org_id}/*`` endpoints, so ``DEVIN_ORG_ID`` is required for
live data. The credential is read from the environment and only ever used
server-side. Every network call degrades gracefully: partial failures (e.g. the
consumption endpoint being unavailable for a given key) never take down the
whole dashboard, they just omit that slice of data.

Authentication uses a single ``Authorization: Bearer <key>`` header, which works
for both v3 service-user tokens (``cog_``) and personal API keys
(``apk_user_``).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from .config import Settings
from .models import Message, PullRequest, Session

logger = logging.getLogger("devin_client")


def _to_epoch(value: Any) -> int:
    """Coerce a timestamp (epoch number or ISO-8601 string) to epoch seconds."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(cleaned).timestamp())
    except ValueError:
        return 0


def _repo_from_pr(url: str) -> str | None:
    # https://github.com/owner/repo/pull/123 -> owner/repo
    try:
        parts = url.split("github.com/", 1)[1].split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    except (IndexError, AttributeError):
        return None
    return None


class DevinClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.org_id:
            raise ValueError("DEVIN_ORG_ID is required for the organization API")
        self._settings = settings
        self._org = settings.org_id
        self._client = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Accept": "application/json",
            },
        )

    @property
    def _org_base(self) -> str:
        return f"/v3/organizations/{self._org}"

    def close(self) -> None:
        self._client.close()

    # -- sessions ---------------------------------------------------------
    def list_sessions(
        self, created_after: int | None = None, max_items: int = 2000
    ) -> list[Session]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(items) < max_items:
            params: dict[str, Any] = {"first": 100}
            if cursor:
                params["after"] = cursor
            if created_after is not None:
                params["created_after"] = created_after
            resp = self._client.get(f"{self._org_base}/sessions", params=params)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("items", [])
            items.extend(batch)
            if not data.get("has_next_page") or not batch:
                break
            cursor = data.get("end_cursor")
            if not cursor:
                break
        sessions = [self._parse_session(raw) for raw in items[:max_items]]
        # Filter client-side too, in case the endpoint ignores created_after.
        if created_after is not None:
            sessions = [s for s in sessions if s.created_at >= created_after]
        return sessions

    @staticmethod
    def _parse_session(raw: dict[str, Any]) -> Session:
        prs: list[PullRequest] = []
        repo: str | None = None
        for pr in raw.get("pull_requests", []) or []:
            url = pr.get("pr_url") or pr.get("url") or ""
            state = pr.get("pr_state") or pr.get("state")
            if url:
                prs.append(PullRequest(url=url, state=state))
                repo = repo or _repo_from_pr(url)
        return Session(
            session_id=raw.get("session_id", ""),
            title=raw.get("title"),
            status=raw.get("status", "unknown"),
            created_at=_to_epoch(raw.get("created_at")),
            updated_at=_to_epoch(raw.get("updated_at") or raw.get("created_at")),
            acus_consumed=float(raw.get("acus_consumed", 0) or 0),
            org_id=raw.get("org_id"),
            user_id=raw.get("user_id") or raw.get("service_user_id"),
            origin=raw.get("origin"),
            category=raw.get("category"),
            repo=repo,
            tags=list(raw.get("tags", []) or []),
            pull_requests=prs,
        )

    # -- consumption ------------------------------------------------------
    def daily_consumption(
        self, time_after: int | None, time_before: int | None
    ) -> list[dict[str, Any]]:
        """Organization-wide daily ACU consumption, broken down by product."""
        try:
            params: dict[str, Any] = {}
            if time_after is not None:
                params["time_after"] = time_after
            if time_before is not None:
                params["time_before"] = time_before
            resp = self._client.get(
                f"{self._org_base}/consumption/daily", params=params
            )
            resp.raise_for_status()
            return resp.json().get("consumption_by_date", [])
        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:  # pragma: no cover - network dependent
            logger.warning("daily_consumption unavailable: %s", exc)
            return []

    # -- messages ---------------------------------------------------------
    def session_messages(self, devin_id: str, max_items: int = 500) -> list[Message]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(items) < max_items:
            params: dict[str, Any] = {"first": 100}
            if cursor:
                params["after"] = cursor
            resp = self._client.get(
                f"{self._org_base}/sessions/{devin_id}/messages", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("items", [])
            items.extend(batch)
            if not data.get("has_next_page") or not batch:
                break
            cursor = data.get("end_cursor")
            if not cursor:
                break
        return [
            Message(
                event_id=m.get("event_id", ""),
                source=m.get("source", "devin"),
                message=m.get("message", ""),
                created_at=_to_epoch(m.get("created_at")),
            )
            for m in items[:max_items]
        ]

    # -- users (best effort) ---------------------------------------------
    def user_names(self, org_ids: list[str]) -> dict[str, str]:
        names: dict[str, str] = {}
        # Always include the configured org; sessions may reference others.
        for org_id in {self._org, *org_ids}:
            path = f"/v3beta1/organizations/{org_id}/members/users"
            try:
                resp = self._client.get(path, params={"first": 100, "limit": 100})
                if resp.status_code != 200:
                    continue
                for u in resp.json().get("items", []):
                    uid = u.get("user_id")
                    name = u.get("name") or u.get("email")
                    if uid and name:
                        names[uid] = name
            except (httpx.HTTPError, ValueError):
                continue
        return names
