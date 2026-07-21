"""Runtime configuration for the observability dashboard backend.

All configuration comes from environment variables so that the Devin API
credential never has to be committed or exposed to the browser. When no
credential is present the app automatically serves a realistic demo dataset,
which makes the dashboard runnable out of the box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.devin.ai"
_DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "state.json"

_TRUE_VALUES = {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    """Immutable view of the process environment."""

    api_key: str | None
    base_url: str
    request_timeout: float

    # Automation (GitHub -> Devin webhook orchestration).
    org_id: str | None
    github_repo: str
    github_token: str | None
    github_webhook_secret: str
    trigger_label: str
    poll_interval_sec: int
    store_path: str

    @property
    def use_mock(self) -> bool:
        """Use the built-in demo dataset when live access isn't configured.

        The organization API needs both a credential and an org id, so demo
        mode is used unless both are present. Setting
        ``DEVIN_DASHBOARD_FORCE_MOCK=1`` forces demo mode even when they are
        (handy for local UI work).
        """
        if os.environ.get("DEVIN_DASHBOARD_FORCE_MOCK", "").strip() in _TRUE_VALUES:
            return True
        return not (self.api_key and self.org_id)

    @property
    def automation_enabled(self) -> bool:
        """Live webhook orchestration needs both a key and an org id."""
        return bool(self.api_key and self.org_id)


def load_settings() -> Settings:
    api_key = (
        os.environ.get("DEVIN_API_KEY")
        or os.environ.get("DEVIN_DASHBOARD_API_KEY")
        or None
    )
    if api_key is not None:
        api_key = api_key.strip() or None

    base_url = os.environ.get("DEVIN_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        timeout = float(os.environ.get("DEVIN_API_TIMEOUT", "30"))
    except ValueError:
        timeout = 30.0

    org_id = os.environ.get("DEVIN_ORG_ID", "").strip() or None
    github_repo = os.environ.get("GITHUB_REPO", "asmitakhaneja/superset").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    github_webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    trigger_label = os.environ.get("TRIGGER_LABEL", "devin-fix").strip() or "devin-fix"
    try:
        poll_interval_sec = int(os.environ.get("POLL_INTERVAL_SEC", "30"))
    except ValueError:
        poll_interval_sec = 30
    store_path = os.environ.get("STORE_PATH", str(_DEFAULT_STORE))

    return Settings(
        api_key=api_key,
        base_url=base_url,
        request_timeout=timeout,
        org_id=org_id,
        github_repo=github_repo,
        github_token=github_token,
        github_webhook_secret=github_webhook_secret,
        trigger_label=trigger_label,
        poll_interval_sec=poll_interval_sec,
        store_path=store_path,
    )
