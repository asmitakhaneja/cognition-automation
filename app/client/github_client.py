"""
Minimal GitHub REST API helper. A personal access token is optional for
public repos but strongly recommended to avoid the 60 req/hr unauthenticated
rate limit.
"""
import requests

from ..settings import GITHUB_TOKEN, GITHUB_REPO

REPO_FULL_NAME = GITHUB_REPO

HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def get_issue(issue_number: int) -> dict:
    resp = requests.get(
        f"https://api.github.com/repos/{REPO_FULL_NAME}/issues/{issue_number}",
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body") or "",
        "labels": [lbl["name"] for lbl in data.get("labels", [])],
    }


def list_labeled_issues(label: str) -> list[dict]:
    """Used by the fallback poller path, and handy for a 'trigger all' demo step."""
    resp = requests.get(
        f"https://api.github.com/repos/{REPO_FULL_NAME}/issues",
        headers=HEADERS,
        params={"labels": label, "state": "open"},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "body": i.get("body") or "",
            "labels": [lbl["name"] for lbl in i.get("labels", [])],
        }
        for i in resp.json()
    ]
