"""
Thin wrapper around the Devin v3 API.

Docs: https://docs.devin.ai/api-reference/overview
Base URL: https://api.devin.ai/v3/organizations/{org_id}/...
Auth: Bearer <service user API key, "cog_..." prefix>
"""
import requests

from ..settings import (
    DEVIN_API_KEY,
    DEVIN_ORG_ID,
    BYPASS_APPROVAL,
    MAX_ACU_LIMIT,
    PLAYBOOK_ID,
    KNOWLEDGE_IDS,
    RESUMABLE,
)

BASE_URL = f"https://api.devin.ai/v3/organizations/{DEVIN_ORG_ID}"

HEADERS = {
    "Authorization": f"Bearer {DEVIN_API_KEY}",
    "Content-Type": "application/json",
}

# Statuses observed as terminal for a session. Kept as a set so the poller
# knows when to stop checking a given session.
TERMINAL_STATUSES = {"finished", "blocked", "expired", "stopped"}


def categorize(issue_title: str, issue_labels: list[str]) -> str:
    """Best-effort bucket for a GitHub issue, used to tag Devin sessions
    so the dashboard can group throughput by category."""
    labels = {lbl.lower() for lbl in issue_labels}
    title = issue_title.lower()

    if "security" in labels or any(k in title for k in ["cve", "vuln", "xss", "auth", "injection"]):
        return "security"
    if "dependencies" in labels or any(
        k in title for k in ["upgrade", "bump", "dependency", "outdated"]
    ):
        return "dependency"
    if "tests" in labels or "test" in title or "coverage" in title:
        return "tests"
    return "quality"


def build_prompt(repo_full_name: str, issue_number: int, issue_title: str, issue_body: str) -> str:
    return f"""
You are fixing GitHub issue #{issue_number} in the repository {repo_full_name}.

Title: {issue_title}

Description:
{issue_body}

Instructions:
1. Clone/checkout the repository and investigate the relevant code path before making any changes.
2. Make the minimal, correct fix. Do not refactor unrelated code or files.
3. Add or update a test that would have caught this issue.
4. Run the existing test suite for the affected module and confirm it passes locally.
5. Commit your changes and open a pull request against the `master` branch of {repo_full_name}.
6. In the PR description, include a short summary of the root cause and the fix, and add the line:
   "Fixes #{issue_number}"
7. If you cannot fully resolve the issue, open a draft PR describing what you tried and why it's blocked,
   rather than leaving no output at all.
""".strip()


def create_session(repo_full_name: str, issue_number: int, issue_title: str,
                    issue_body: str, category: str) -> dict:
    """Create a new Devin session to remediate a GitHub issue."""
    payload = {
        "prompt": build_prompt(repo_full_name, issue_number, issue_title, issue_body),
        "title": f"Fix #{issue_number}: {issue_title}"[:120],
        "tags": ["automation", category],
        "repos": [repo_full_name],
        "idempotent": True,
    }

    if BYPASS_APPROVAL is not None:
        payload["bypass_approval"] = BYPASS_APPROVAL
    if MAX_ACU_LIMIT is not None:
        payload["max_acu_limit"] = MAX_ACU_LIMIT
    if PLAYBOOK_ID is not None:
        payload["playbook_id"] = PLAYBOOK_ID
    if KNOWLEDGE_IDS:
        payload["knowledge_ids"] = KNOWLEDGE_IDS
    if RESUMABLE is not None:
        payload["resumable"] = RESUMABLE

    resp = requests.post(f"{BASE_URL}/sessions", headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_session(session_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_message(session_id: str, message: str) -> dict:
    """Send a follow-up instruction to a running/suspended session.
    Demonstrates programmatic *management* of a session, not just fire-and-forget."""
    resp = requests.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        headers=HEADERS,
        json={"message": message},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_sessions_insights(limit: int = 50) -> dict:
    """Pull Devin's own AI-generated session insights for the dashboard/report."""
    resp = requests.get(
        f"{BASE_URL}/sessions-insights",
        headers=HEADERS,
        params={"limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_status_and_pr(session_data: dict) -> tuple[str, str | None]:
    """Normalize whatever the session payload gives us into (status, pr_url)."""
    status = session_data.get("status") or session_data.get("status_enum") or "unknown"
    pr_url = None
    pr = session_data.get("pull_request") or session_data.get("pr")
    if isinstance(pr, dict):
        pr_url = pr.get("url") or pr.get("html_url")
    # Some responses may list PRs under structured_output / metadata; fall back gracefully.
    if not pr_url:
        structured = session_data.get("structured_output") or {}
        pr_url = structured.get("pr_url")
    return status, pr_url
