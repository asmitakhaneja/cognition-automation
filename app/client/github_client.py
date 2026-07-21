"""
Minimal GitHub REST API helper. A personal access token is optional for
public repos but strongly recommended to avoid the 60 req/hr unauthenticated
rate limit.
"""
import logging

import requests

from ..settings import GITHUB_TOKEN, GITHUB_REPO

logger = logging.getLogger(__name__)

REPO_FULL_NAME = GITHUB_REPO

HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
else:
    logger.warning(
        "GITHUB_TOKEN is not set; requests will be unauthenticated "
        "(rate-limited to 60 req/hr)"
    )


def get_issue(issue_number: int) -> dict:
    logger.debug("Fetching issue #%d from %s", issue_number, REPO_FULL_NAME)
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{REPO_FULL_NAME}/issues/{issue_number}",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "GitHub get_issue failed for #%d (HTTP %d): %s",
            issue_number, resp.status_code, resp.text,
        )
        raise
    data = resp.json()
    logger.info("Fetched issue #%d: '%s'", issue_number, data.get("title"))
    return {
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body") or "",
        "labels": [lbl["name"] for lbl in data.get("labels", [])],
    }


def list_labeled_issues(label: str) -> list[dict]:
    """Used by the fallback poller path, and handy for a 'trigger all' demo step."""
    logger.debug("Listing open issues labelled '%s' in %s", label, REPO_FULL_NAME)
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{REPO_FULL_NAME}/issues",
            headers=HEADERS,
            params={"labels": label, "state": "open"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "GitHub list_labeled_issues failed for label '%s' (HTTP %d): %s",
            label, resp.status_code, resp.text,
        )
        raise
    issues = resp.json()
    logger.info(
        "Found %d open issue(s) with label '%s' in %s",
        len(issues), label, REPO_FULL_NAME,
    )
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "body": i.get("body") or "",
            "labels": [lbl["name"] for lbl in i.get("labels", [])],
        }
        for i in issues
    ]
