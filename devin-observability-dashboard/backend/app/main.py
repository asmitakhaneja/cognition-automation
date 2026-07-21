"""FastAPI application entrypoint.

Exposes a small, normalized JSON API for the dashboard frontend and serves the
built single-page app. In demo mode it runs entirely on the bundled synthetic
dataset; with a credential configured it proxies the live Devin API.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import mock_data
from .aggregate import build_overview
from .config import load_settings
from .devin_client import DevinClient
from .models import MessagesResponse, Overview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

settings = load_settings()
app = FastAPI(title="Devin Observability Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Very small in-process TTL cache to avoid hammering the API on every reload.
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 120.0


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _cache_set(key: str, value: object) -> None:
    _CACHE[key] = (time.time(), value)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "demo": settings.use_mock}


@app.get("/api/overview", response_model=Overview)
def overview(days: int = Query(default=30, ge=1, le=90)) -> Overview:
    cache_key = f"overview:{days}:{settings.use_mock}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    if settings.use_mock:
        sessions = [s for s in mock_data.generate_sessions()]
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        sessions = [s for s in sessions if s.created_at >= cutoff]
        result = build_overview(sessions, range_days=days, is_demo=True)
        _cache_set(cache_key, result)
        return result

    client = DevinClient(settings)
    try:
        created_after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        sessions = client.list_sessions(created_after=created_after)
        time_after = created_after
        time_before = int(time.time())
        consumption = client.daily_consumption(time_after, time_before)
        org_ids = sorted({s.org_id for s in sessions if s.org_id})
        user_names = client.user_names(org_ids)
        result = build_overview(
            sessions,
            range_days=days,
            is_demo=False,
            consumption_by_date=consumption,
            user_names=user_names,
        )
        _cache_set(cache_key, result)
        return result
    except Exception as exc:  # noqa: BLE001 - surface upstream failures cleanly
        logger.exception("overview failed")
        raise HTTPException(status_code=502, detail=f"Devin API error: {exc}") from exc
    finally:
        client.close()


@app.get("/api/sessions/{session_id}/messages", response_model=MessagesResponse)
def session_messages(session_id: str) -> MessagesResponse:
    if settings.use_mock:
        target = next(
            (s for s in mock_data.generate_sessions() if s.session_id == session_id),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return MessagesResponse(
            session_id=session_id, is_demo=True, items=mock_data.generate_messages(target)
        )

    client = DevinClient(settings)
    try:
        items = client.session_messages(session_id)
        return MessagesResponse(session_id=session_id, is_demo=False, items=items)
    except Exception as exc:  # noqa: BLE001
        logger.exception("messages failed")
        raise HTTPException(status_code=502, detail=f"Devin API error: {exc}") from exc
    finally:
        client.close()


# -- static frontend --------------------------------------------------------
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
