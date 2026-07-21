"""Runtime configuration for the observability dashboard backend.

All configuration comes from environment variables so that the Devin API
credential never has to be committed or exposed to the browser. When no
credential is present the app automatically serves a realistic demo dataset,
which makes the dashboard runnable out of the box.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_BASE_URL = "https://api.devin.ai"


@dataclass(frozen=True)
class Settings:
    """Immutable view of the process environment."""

    api_key: str | None
    base_url: str
    request_timeout: float

    @property
    def use_mock(self) -> bool:
        """Use the built-in demo dataset when no credential is configured.

        Setting ``DEVIN_DASHBOARD_FORCE_MOCK=1`` forces demo mode even when a
        key is present (handy for local UI work).
        """
        if os.environ.get("DEVIN_DASHBOARD_FORCE_MOCK", "").strip() in {"1", "true", "yes"}:
            return True
        return not bool(self.api_key)


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

    return Settings(api_key=api_key, base_url=base_url, request_timeout=timeout)
