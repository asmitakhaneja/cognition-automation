"""Minimal GitHub REST helper for the automation orchestrator.

A token is optional for public repos but strongly recommended to avoid the
60 req/hr unauthenticated rate limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("automation.github")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: list[str] = field(default_factory=list)


class GitHubClient:
    def __init__(
        self, repo: str, token: str | None = None, timeout: float = 15.0
    ) -> None:
        self.repo = repo
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                "GITHUB_TOKEN not set; GitHub requests are rate-limited to 60/hr"
            )
        self._client = httpx.Client(
            base_url="https://api.github.com", headers=headers, timeout=timeout
        )

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _to_issue(raw: dict) -> Issue:
        return Issue(
            number=int(raw["number"]),
            title=raw.get("title", ""),
            body=raw.get("body") or "",
            labels=[lbl["name"] for lbl in raw.get("labels", [])],
        )

    def get_issue(self, issue_number: int) -> Issue:
        resp = self._client.get(f"/repos/{self.repo}/issues/{issue_number}")
        resp.raise_for_status()
        return self._to_issue(resp.json())

    def list_labeled_issues(self, label: str) -> list[Issue]:
        resp = self._client.get(
            f"/repos/{self.repo}/issues",
            params={"labels": label, "state": "open"},
        )
        resp.raise_for_status()
        return [self._to_issue(raw) for raw in resp.json()]
