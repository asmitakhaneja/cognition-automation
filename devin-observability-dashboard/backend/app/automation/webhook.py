"""GitHub webhook receiver + manual trigger endpoints.

Verifies the webhook signature, filters for ``issues`` events carrying the
configured trigger label, and hands off to the orchestrator. Mounted under
``/api`` by the main app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Callable
from urllib.parse import unquote_plus

from fastapi import APIRouter, HTTPException, Request

from ..config import Settings
from ..models import TriggerResult
from .orchestrator import Orchestrator
from .store import Store

logger = logging.getLogger("automation.webhook")

_HANDLED_ACTIONS = {"labeled", "opened", "reopened"}


def verify_signature(
    secret: str, raw_body: bytes, signature_header: str | None
) -> bool:
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not set; skipping verification")
        return True
    if not signature_header:
        return False
    expected = (
        "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def parse_payload(raw_body: bytes, content_type: str) -> dict:
    """GitHub sends url-encoded ``payload=<json>`` unless content type is JSON."""
    if "application/x-www-form-urlencoded" in content_type:
        decoded = unquote_plus(raw_body.decode())
        return json.loads(decoded.removeprefix("payload="))
    return json.loads(raw_body)


def create_router(
    settings: Settings,
    store: Store,
    make_orchestrator: Callable[[], Orchestrator],
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/github", response_model=TriggerResult)
    async def github_webhook(request: Request) -> TriggerResult:
        raw_body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(settings.github_webhook_secret, raw_body, signature):
            raise HTTPException(status_code=401, detail="invalid signature")

        event = request.headers.get("X-GitHub-Event", "")
        payload = parse_payload(raw_body, request.headers.get("Content-Type", ""))
        action = payload.get("action")
        issue = payload.get("issue", {})
        issue_number = issue.get("number")
        logger.info(
            "Webhook: event=%s action=%s issue=#%s", event, action, issue_number
        )

        if event != "issues":
            return TriggerResult(skipped=True, reason=f"event {event} ignored")
        if action not in _HANDLED_ACTIONS:
            return TriggerResult(skipped=True, reason=f"action {action} ignored")

        labels = [lbl["name"] for lbl in issue.get("labels", [])]
        if settings.trigger_label not in labels:
            return TriggerResult(
                skipped=True,
                reason=f"missing label '{settings.trigger_label}'",
            )

        orchestrator = make_orchestrator()
        try:
            return orchestrator.trigger(
                store,
                issue_number=issue["number"],
                title=issue["title"],
                body=issue.get("body") or "",
                labels=labels,
            )
        finally:
            orchestrator.close()

    @router.post("/trigger/{issue_number}", response_model=TriggerResult)
    def manual_trigger(issue_number: int) -> TriggerResult:
        orchestrator = make_orchestrator()
        try:
            issue = orchestrator.github.get_issue(issue_number)
            return orchestrator.trigger(
                store,
                issue_number=issue.number,
                title=issue.title,
                body=issue.body,
                labels=issue.labels,
            )
        finally:
            orchestrator.close()

    @router.post("/trigger-all", response_model=list[TriggerResult])
    def manual_trigger_all() -> list[TriggerResult]:
        orchestrator = make_orchestrator()
        results: list[TriggerResult] = []
        try:
            for issue in orchestrator.github.list_labeled_issues(
                settings.trigger_label
            ):
                results.append(
                    orchestrator.trigger(
                        store,
                        issue_number=issue.number,
                        title=issue.title,
                        body=issue.body,
                        labels=issue.labels,
                    )
                )
            return results
        finally:
            orchestrator.close()

    return router
