"""
Thin wrapper around the Devin v3 API.

Docs: https://docs.devin.ai/api-reference/overview
Base URL: https://api.devin.ai/v3/organizations/{org_id}/...
Auth: Bearer <service user API key, "cog_..." prefix>
"""
import logging

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

logger = logging.getLogger(__name__)

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
        category = "security"
    elif "dependencies" in labels or any(
        k in title for k in ["upgrade", "bump", "dependency", "outdated"]
    ):
        category = "dependency"
    elif "tests" in labels or "test" in title or "coverage" in title:
        category = "tests"
    else:
        category = "quality"

    logger.debug("Issue '%s' categorised as '%s'", issue_title, category)
    return category


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
    logger.info(
        "Creating Devin session for issue #%d '%s' (category=%s)",
        issue_number, issue_title, category,
    )
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

    try:
        resp = requests.post(f"{BASE_URL}/sessions", headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Devin create_session failed (HTTP %d): %s",
            resp.status_code, resp.text,
        )
        raise

    data = resp.json()
    session_id = data.get("session_id") or data.get("id")
    logger.info("Devin session created: session_id=%s", session_id)
    return data


def get_session(session_id: str) -> dict:
    logger.debug("Fetching Devin session %s", session_id)
    try:
        resp = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Devin get_session failed for %s (HTTP %d): %s",
            session_id, resp.status_code, resp.text,
        )
        raise
    data = resp.json()
    logger.debug("Fetched session %s (HTTP %d): %s", session_id, resp.status_code, data)
    return data


def send_message(session_id: str, message: str) -> dict:
    """Send a follow-up instruction to a running/suspended session.
    Demonstrates programmatic *management* of a session, not just fire-and-forget."""
    logger.info(
        "Sending message to session %s: %.80s%s",
        session_id, message, "..." if len(message) > 80 else "",
    )
    try:
        resp = requests.post(
            f"{BASE_URL}/sessions/{session_id}/messages",
            headers=HEADERS,
            json={"message": message},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Devin send_message failed for session %s (HTTP %d): %s",
            session_id, resp.status_code, resp.text,
        )
        raise
    return resp.json()


def list_sessions_insights(limit: int = 50) -> dict:
    """Pull Devin's own AI-generated session insights for the dashboard/report."""
    logger.debug("Fetching sessions insights (limit=%d)", limit)
    try:
        resp = requests.get(
            f"{BASE_URL}/sessions-insights",
            headers=HEADERS,
            params={"limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Devin list_sessions_insights failed (HTTP %d): %s",
            resp.status_code, resp.text,
        )
        raise
    return resp.json()


def extract_status_and_pr(session_data: dict) -> tuple[str, str | None, str | None]:
    """Normalize whatever the session payload gives us into (status, pr_url, pr_status)."""

    status = session_data.get("status") or session_data.get("status_enum") or "unknown"
    pr_url = None
    pr_status = None
    pr_list = session_data.get("pull_requests") or session_data.get("pr")
    pr = pr_list[0] if isinstance(pr_list, list) and pr_list else pr_list
    if isinstance(pr, dict):
        pr_url = pr.get("pr_url")
        pr_status = pr.get("pr_state")
    if not pr_url:
        structured = session_data.get("structured_output") or {}
        pr_url = structured.get("pr_url")
    return status, pr_url, pr_status


def _get_single_session_insights(session_id: str) -> dict | None:
    """GET the per-session insights, kicking off generation if none exist yet.

    Best-effort: returns the insights object if available, otherwise ``None``.
    The AI-generated ``analysis`` block is produced asynchronously, and for a
    session that is still running the endpoint commonly 404s (nothing generated
    yet) or returns an object whose ``acus_consumed`` is still ``null``. The
    ``/generate`` response is only a kickoff acknowledgement (no metrics), so we
    always re-GET rather than returning it. Generation failures are non-fatal —
    we never let them wipe out metrics that another source can provide.
    """
    url = f"{BASE_URL}/sessions/{session_id}/insights"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404 or not resp.text.strip():
            logger.info("No insights for session %s — generating", session_id)
            try:
                requests.post(f"{url}/generate", headers=HEADERS, timeout=30)
            except Exception:
                logger.debug("Insights generation kickoff failed for %s", session_id, exc_info=True)
            resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404 or not resp.text.strip():
            return None
        resp.raise_for_status()
        data = resp.json()
        logger.debug("Per-session insights for %s: %s", session_id, data)
        return data or None
    except Exception:
        logger.warning("Could not fetch per-session insights for %s", session_id, exc_info=True)
        return None


def _get_live_session_insight(session_id: str) -> dict | None:
    """Find this session in the bulk ``/sessions-insights`` feed.

    Unlike the per-session endpoint, the bulk feed reports ``acus_consumed`` for
    in-flight (running) sessions, so it is the reliable source of *live* compute
    usage before a session finishes.
    """
    try:
        payload = list_sessions_insights()
    except Exception:
        logger.warning("Could not fetch bulk sessions-insights", exc_info=True)
        return None

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("insights")
            or payload.get("sessions")
            or payload.get("items")
            or payload.get("data")
            or []
        )
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        session = item.get("session") if isinstance(item.get("session"), dict) else {}
        sid = item.get("session_id") or item.get("id") or session.get("session_id")
        if sid == session_id:
            return item
    return None


def get_session_insights(session_id: str) -> dict | None:
    """Return per-session insights, ensuring ``acus_consumed`` is populated for
    running sessions too.

    Compute usage (``acus_consumed``) accrues while a session is still running,
    but the per-session ``/insights`` endpoint only exposes it once insights have
    been generated (typically at/after completion). Relying on it alone leaves
    ACUs empty for live sessions — including ones that have already opened a PR
    but are not yet ``finished``. To fix that we merge in the bulk
    ``/sessions-insights`` feed, which reports ACUs for in-flight sessions,
    whenever the per-session payload is missing the metric.
    """
    per_session = _get_single_session_insights(session_id)
    if per_session and per_session.get("acus_consumed") is not None:
        return per_session

    live = _get_live_session_insight(session_id)
    if live is None:
        return per_session
    if per_session is None:
        return live

    merged = dict(per_session)
    for key in ("acus_consumed", "session_size"):
        if merged.get(key) is None and live.get(key) is not None:
            merged[key] = live[key]
    return merged


def get_session_messages(session_id: str) -> list[dict]:
    """Fetch the full message thread for a session."""
    try:
        resp = requests.get(
            f"{BASE_URL}/sessions/{session_id}/messages",
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("messages") or data.get("items", [])
    except Exception:
        logger.warning("Could not fetch messages for session %s", session_id, exc_info=True)
        return []


def extract_insights_fields(insights: dict) -> dict:
    """Normalise a Devin insights payload into flat store fields."""
    clf = (insights.get("analysis") or {}).get("classification") or insights.get("classification") or {}
    return {
        "acus_consumed": insights.get("acus_consumed"),
        "session_size": insights.get("session_size"),
        "classification_category": clf.get("category"),
        "classification_confidence": clf.get("confidence"),
        "tools_and_frameworks": clf.get("tools_and_frameworks", []),
        "programming_languages": clf.get("programming_languages", []),
    }
