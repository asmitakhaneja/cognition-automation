"""Turns a labeled GitHub issue into a managed Devin session.

This is the *write* side of the Devin API (session creation + polling), kept
separate from the read-only dashboard client. It reuses the same base URL and
bearer credential from :class:`~app.config.Settings`.
"""

from __future__ import annotations

import logging
import time

import httpx

from ..config import Settings
from ..models import AutomationRecord, TriggerResult
from .github_client import GitHubClient
from .store import Store

logger = logging.getLogger("automation.orchestrator")


def categorize(title: str, labels: list[str]) -> str:
    """Best-effort bucket for an issue, mirrored on Devin session tags."""
    label_set = {lbl.lower() for lbl in labels}
    text = title.lower()
    security = ("cve", "vuln", "xss", "auth", "injection")
    dependency = ("upgrade", "bump", "dependency", "outdated")
    if "security" in label_set or any(k in text for k in security):
        return "security"
    if "dependencies" in label_set or any(k in text for k in dependency):
        return "dependency"
    if "tests" in label_set or "test" in text or "coverage" in text:
        return "tests"
    return "quality"


def build_prompt(repo: str, number: int, title: str, body: str) -> str:
    return f"""
You are fixing GitHub issue #{number} in the repository {repo}.

Title: {title}

Description:
{body}

Instructions:
1. Investigate the relevant code path before making any changes.
2. Make the minimal, correct fix. Do not refactor unrelated code.
3. Add or update a test that would have caught this issue.
4. Run the affected module's tests and confirm they pass.
5. Open a pull request against the default branch, including "Fixes #{number}".
6. If you cannot fully resolve it, open a draft PR describing what is blocked.
""".strip()


class Orchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.github = GitHubClient(
            repo=settings.github_repo,
            token=settings.github_token,
            timeout=settings.request_timeout,
        )
        self._devin = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._devin.close()
        self.github.close()

    @property
    def _sessions_url(self) -> str:
        return f"/v3/organizations/{self._settings.org_id}/sessions"

    def create_session(self, number: int, title: str, body: str, category: str) -> dict:
        payload = {
            "prompt": build_prompt(self._settings.github_repo, number, title, body),
            "title": f"Fix #{number}: {title}"[:120],
            "tags": ["automation", category],
            "repos": [self._settings.github_repo],
            "idempotent": True,
        }
        resp = self._devin.post(self._sessions_url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_session(self, session_id: str) -> dict:
        resp = self._devin.get(f"{self._sessions_url}/{session_id}")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def extract_status_and_pr(data: dict) -> tuple[str, str | None]:
        status = data.get("status") or data.get("status_enum") or "unknown"
        pr = data.get("pull_request") or data.get("pr")
        pr_url = None
        if isinstance(pr, dict):
            pr_url = pr.get("url") or pr.get("html_url")
        if not pr_url:
            structured = data.get("structured_output") or {}
            if isinstance(structured, dict):
                pr_url = structured.get("pr_url")
        return status, pr_url

    def trigger(
        self,
        store: Store,
        issue_number: int,
        title: str,
        body: str,
        labels: list[str],
    ) -> TriggerResult:
        existing = store.get(issue_number)
        if existing and existing.session_id:
            logger.info(
                "Skipping issue #%d — session already exists: %s",
                issue_number,
                existing.session_id,
            )
            return TriggerResult(
                skipped=True, reason="already triggered", record=existing
            )

        category = categorize(title, labels)
        logger.info(
            "Triggering remediation for issue #%d (category=%s)",
            issue_number,
            category,
        )
        session = self.create_session(issue_number, title, body, category)
        session_id = session.get("session_id") or session.get("id")
        record = store.upsert(
            issue_number,
            title=title,
            category=category,
            session_id=session_id,
            session_url=session.get("url"),
            status="running",
            created_at=time.time(),
        )
        return TriggerResult(skipped=False, record=record)

    def poll_once(self, store: Store) -> None:
        for record in store.active():
            if not record.session_id:
                continue
            try:
                data = self.get_session(record.session_id)
            except httpx.HTTPError:
                logger.warning(
                    "Poll failed for issue #%d", record.issue_number, exc_info=True
                )
                continue
            status, pr_url = self.extract_status_and_pr(data)
            store.upsert(
                record.issue_number,
                status=status,
                pr_url=pr_url or record.pr_url,
            )


def demo_records() -> list[AutomationRecord]:
    """Seed data so the automation panel renders without live credentials."""
    now = time.time()
    hour = 3600.0
    return [
        AutomationRecord(
            issue_number=412,
            title="XSS in dashboard markdown renderer",
            category="security",
            status="finished",
            session_id="devin-demo-412",
            session_url="https://app.devin.ai/sessions/demo-412",
            pr_url="https://github.com/asmitakhaneja/superset/pull/9412",
            created_at=now - 6 * hour,
            updated_at=now - 5 * hour,
        ),
        AutomationRecord(
            issue_number=418,
            title="Bump sqlparse to patch ReDoS advisory",
            category="dependency",
            status="finished",
            session_id="devin-demo-418",
            session_url="https://app.devin.ai/sessions/demo-418",
            pr_url="https://github.com/asmitakhaneja/superset/pull/9418",
            created_at=now - 4 * hour,
            updated_at=now - 3.4 * hour,
        ),
        AutomationRecord(
            issue_number=421,
            title="Flaky test in test_sql_lab.py",
            category="tests",
            status="running",
            session_id="devin-demo-421",
            session_url="https://app.devin.ai/sessions/demo-421",
            created_at=now - 40 * 60,
            updated_at=now - 5 * 60,
        ),
        AutomationRecord(
            issue_number=425,
            title="Null deref when chart has no datasource",
            category="quality",
            status="blocked",
            session_id="devin-demo-425",
            session_url="https://app.devin.ai/sessions/demo-425",
            created_at=now - 2 * hour,
            updated_at=now - 90 * 60,
        ),
    ]
