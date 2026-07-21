import asyncio
import hashlib
import hmac
import html as _html
import json
import logging
import os
import threading
import time
from urllib.parse import unquote_plus

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from . import store
from .client import devin_client, github_client
from .settings import (
    GITHUB_WEBHOOK_SECRET as WEBHOOK_SECRET,
    TRIGGER_LABEL,
    WATCHER_POLL_SEC,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Devin x Superset Remediation Orchestrator")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _relative_time(ts: float | None) -> str:
    if not ts:
        return '—'
    sec = int(time.time() - ts)
    if sec < 60:
        return f'{sec}s ago'
    if sec < 3600:
        return f'{sec // 60}m ago'
    if sec < 86400:
        return f'{sec // 3600}h ago'
    return f'{sec // 86400}d ago'

# --------------------------------------------------------------------------
# SSE broadcast: a list of per-client asyncio queues.
# Watcher threads put events here; the /events endpoint drains them.
# --------------------------------------------------------------------------
_sse_subscribers: list[asyncio.Queue] = []
_sse_lock = threading.Lock()


def _broadcast(event: dict) -> None:
    """Push an event to every connected SSE client (called from watcher threads)."""
    data = json.dumps(event)
    with _sse_lock:
        for q in _sse_subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass


# --------------------------------------------------------------------------
# Webhook signature verification
# --------------------------------------------------------------------------
def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not WEBHOOK_SECRET:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET is not set; skipping signature verification"
        )
        return True
    if not signature_header:
        logger.warning("Webhook received with no X-Hub-Signature-256 header")
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        logger.warning("Webhook signature mismatch — request rejected")
        return False
    return True


# --------------------------------------------------------------------------
# Per-session watcher: replaces the old global poll_loop.
# One thread per active session; exits once a terminal status is reached.
# --------------------------------------------------------------------------
def _session_watcher(session_id: str, issue_number: int) -> None:
    logger.info(
        "Watcher started for issue #%d (session_id=%s, interval=%ds)",
        issue_number, session_id, WATCHER_POLL_SEC,
    )
    while True:
        time.sleep(WATCHER_POLL_SEC)
        try:
            data = devin_client.get_session(session_id)
            new_status, pr_url, pr_status = devin_client.extract_status_and_pr(data)
            status_detail = (
                data.get("status_detail") or data.get("status_reason") or None
            )

            record = store.get_record(issue_number) or {}
            old_status = record.get("status")

            if new_status != old_status:
                logger.info(
                    "Issue #%d status changed: %s -> %s",
                    issue_number, old_status, new_status,
                )
            if pr_url and not record.get("pr_url"):
                logger.info("PR opened for issue #%d: %s", issue_number, pr_url)

            # Fetch messages on every tick (non-fatal)
            messages = devin_client.get_session_messages(session_id)
            num_user = sum(1 for m in messages if m.get("source") == "user")
            num_devin = sum(1 for m in messages if m.get("source") in ("assistant", "devin"))

            upsert_kwargs = dict(
                status=new_status,
                pr_url=pr_url or record.get("pr_url"),
                pr_status=pr_status,
                status_detail=status_detail,
                messages=messages,
                num_user_messages=num_user,
                num_devin_messages=num_devin,
            )

            # Fetch insights on every tick so ACUs stay current (non-fatal)
            insights = devin_client.get_session_insights(session_id)
            if insights:
                upsert_kwargs.update(devin_client.extract_insights_fields(insights))

            store.upsert_record(issue_number, **upsert_kwargs)
            _broadcast({
                "issue_number": issue_number,
                "status": new_status,
                "pr_url": pr_url or record.get("pr_url"),
                "pr_status": pr_status,
            })

            if new_status in devin_client.TERMINAL_STATUSES:
                logger.info(
                    "Watcher exiting for issue #%d — terminal status '%s'",
                    issue_number, new_status,
                )
                break
        except Exception:
            logger.error(
                "Watcher error for issue #%d (session_id=%s)",
                issue_number, session_id, exc_info=True,
            )


def start_session_watcher(session_id: str, issue_number: int) -> None:
    t = threading.Thread(
        target=_session_watcher,
        args=(session_id, issue_number),
        daemon=True,
        name=f"watcher-issue-{issue_number}",
    )
    t.start()


# --------------------------------------------------------------------------
# Core trigger logic, shared by the webhook path and the manual trigger path
# --------------------------------------------------------------------------
def trigger_remediation(
    issue_number: int, title: str, body: str, labels: list[str]
) -> dict:
    existing = store.get_record(issue_number)
    if existing and existing.get("session_id"):
        logger.info(
            "Skipping issue #%d — session already exists: %s",
            issue_number, existing["session_id"],
        )
        return {"skipped": True, "reason": "already triggered", "record": existing}

    category = devin_client.categorize(title, labels)
    logger.info(
        "Triggering remediation for issue #%d '%s' (category=%s)",
        issue_number, title, category,
    )
    session = devin_client.create_session(
        repo_full_name=github_client.REPO_FULL_NAME,
        issue_number=issue_number,
        issue_title=title,
        issue_body=body,
        category=category,
    )
    session_id = session.get("session_id") or session.get("id")
    session_url = session.get("url")
    logger.info(
        "Session created for issue #%d: session_id=%s url=%s",
        issue_number, session_id, session_url,
    )

    record = store.upsert_record(
        issue_number,
        title=title,
        category=category,
        session_id=session_id,
        session_url=session_url,
        status="running",
        pr_url=None,
        created_at=time.time(),
    )
    start_session_watcher(session_id, issue_number)
    return {"skipped": False, "record": record}


# --------------------------------------------------------------------------
# GitHub webhook endpoint
# --------------------------------------------------------------------------
@app.post("/webhook/github")
async def github_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    content_type = request.headers.get("Content-Type", "")

    if "application/x-www-form-urlencoded" in content_type:
        # GitHub sends payload=<url-encoded-json> when webhook content type
        # is set to application/x-www-form-urlencoded (the GitHub default).
        decoded = unquote_plus(raw_body.decode())
        json_str = decoded.removeprefix("payload=")
        payload = json.loads(json_str)
    else:
        payload = json.loads(raw_body)

    action = payload.get("action")
    issue = payload.get("issue", {})
    issue_number = issue.get("number")

    logger.info(
        "Webhook received: event=%s action=%s issue=#%s",
        event, action, issue_number,
    )

    if event != "issues":
        logger.info("Ignoring webhook: event type '%s' not handled", event)
        return {"ignored": True, "reason": f"event type {event} not handled"}

    labels = [lbl["name"] for lbl in issue.get("labels", [])]

    if action not in ("labeled", "opened"):
        logger.info("Ignoring webhook: action '%s' not handled", action)
        return {"ignored": True, "reason": f"action {action} not handled"}

    if TRIGGER_LABEL not in labels:
        logger.info(
            "Ignoring webhook: issue #%d missing trigger label '%s'",
            issue_number, TRIGGER_LABEL,
        )
        return {"ignored": True, "reason": f"missing label '{TRIGGER_LABEL}'"}

    result = trigger_remediation(
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        labels=labels,
    )
    return JSONResponse(result)


# --------------------------------------------------------------------------
# Manual trigger endpoints (useful for the demo / when webhook infra is down)
# --------------------------------------------------------------------------
@app.post("/trigger/{issue_number}")
def manual_trigger(issue_number: int):
    logger.info("Manual trigger for issue #%d", issue_number)
    issue = github_client.get_issue(issue_number)
    result = trigger_remediation(
        issue_number=issue["number"],
        title=issue["title"],
        body=issue["body"],
        labels=issue["labels"],
    )
    return result


@app.post("/trigger-all")
def manual_trigger_all():
    logger.info("Manual trigger-all for label '%s'", TRIGGER_LABEL)
    issues = github_client.list_labeled_issues(TRIGGER_LABEL)
    logger.info("Found %d issue(s) to trigger", len(issues))
    results = []
    for issue in issues:
        results.append(trigger_remediation(
            issue_number=issue["number"],
            title=issue["title"],
            body=issue["body"],
            labels=issue["labels"],
        ))
    return {"triggered": len(results), "results": results}


@app.post("/session/{issue_number}/message")
def send_followup_message(issue_number: int, message: str):
    """Demonstrates programmatic *management* of an in-flight session,
    not just fire-and-forget session creation."""
    record = store.get_record(issue_number)
    if not record or not record.get("session_id"):
        raise HTTPException(status_code=404, detail="no session for this issue")
    logger.info(
        "Sending follow-up to session %s for issue #%d",
        record["session_id"], issue_number,
    )
    result = devin_client.send_message(record["session_id"], message)
    return result


# --------------------------------------------------------------------------
# Observability: status API + simple HTML dashboard
# --------------------------------------------------------------------------
@app.get("/status")
def status():
    return {
        "summary": store.summary(),
        "records": store.all_records(),
    }


@app.get("/events")
async def sse_events(request: Request):
    """Server-Sent Events stream — pushes a JSON update whenever a session
    status changes so the dashboard can reload without polling."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    with _sse_lock:
        _sse_subscribers.append(queue)
    logger.debug("SSE client connected (total=%d)", len(_sse_subscribers))

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            with _sse_lock:
                _sse_subscribers.remove(queue)
            logger.debug("SSE client disconnected (total=%d)", len(_sse_subscribers))

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    s = store.summary()
    records = store.all_records()

    def _row_pair(r: dict) -> str:
        n = r['issue_number']
        tools = ", ".join(
            (r.get('tools_and_frameworks') or []) + (r.get('programming_languages') or [])
        )
        tools_html = f'<br><small class="tools">{tools}</small>' if tools else ''
        detail = r.get('status_detail') or ''
        detail_html = f'<br><small class="detail">{detail}</small>' if detail else ''
        acus = r.get('acus_consumed')
        acus_html = str(round(float(acus), 1)) if acus is not None else '—'
        clf_conf = r.get('classification_confidence')
        conf_html = (
            f'<br><small class="detail">conf: {round(clf_conf, 2)}</small>'
            if clf_conf is not None else ''
        )

        msgs = r.get('messages') or []
        if msgs:
            def _bubble(m, idx):
                src = m.get("source", "unknown")
                is_user = src == "user"
                role_cls = "bubble-user" if is_user else "bubble-devin"
                avatar_cls = "avatar-user" if is_user else "avatar-devin"
                avatar_label = "You" if is_user else "Dev"
                label = "You" if is_user else "Devin"
                raw_ts = m.get("created_at")
                ts_html = f'<span style="margin-left:6px">{raw_ts}</span>' if raw_ts else ""
                text = _html.escape(m.get("message", "") or m.get("content", ""))
                return (
                    f'<div class="bubble-row {role_cls}">'
                    f'<div class="avatar {avatar_cls}">{avatar_label}</div>'
                    f'<div class="bubble">'
                    f'<div class="bubble-meta"><strong>{label}</strong>{ts_html}</div>'
                    f'<div class="bubble-text" id="bt-{n}-{idx}">{text}</div>'
                    f'<button class="expand-btn" onclick="toggleBubble(\'bt-{n}-{idx}\',this)">Show more</button>'
                    f'</div></div>'
                )
            msg_items = "".join(_bubble(m, i) for i, m in enumerate(msgs))
        else:
            msg_items = '<p style="color:#475569;font-size:0.8rem;text-align:center;padding:1rem 0">No messages yet.</p>'

        msg_count = len(msgs)
        msg_badge = f'<span class="msg-badge">{msg_count}</span>' if msg_count else ''
        pr_link = f'<a href="{r["pr_url"]}" target="_blank">PR ↗</a>' if r.get("pr_url") else "—"
        session_link = (
            f'<a href="{r["session_url"]}" target="_blank">{msg_badge}session ↗</a> ▶'
            if r.get("session_url") else "—"
        )
        data_row = (
            f'<tr data-issue="{n}" title="Click to toggle session log">'
            f'<td>#{n}</td>'
            f'<td>{r.get("title","")}</td>'
            f'<td><span class="tag">{r.get("category","")}</span>{conf_html}{tools_html}</td>'
            f'<td class="ts">{_relative_time(r.get("created_at"))}</td>'
            f'<td class="status-{r.get("status","unknown")}">{r.get("status","unknown")}{detail_html}</td>'
            f'<td>{pr_link}</td>'
            f'<td><span class="tag pr-{r.get("pr_status","")}">{r.get("pr_status") or "—"}</span></td>'
            f'<td class="ts">{acus_html}</td>'
            f'<td>{session_link}</td>'
            f'</tr>'
        )
        log_row = (
            f'<tr id="log-{n}" style="display:none">'
            f'<td colspan="9" class="log-cell">'
            f'<div class="log-panel">'
            f'<div class="log-header">'
            f'<span><strong>Session log</strong> · issue #{n} · {msg_count} message{"s" if msg_count != 1 else ""}</span>'
            f'<span class="log-close" onclick="event.stopPropagation();document.getElementById(\'log-{n}\').style.display=\'none\'">✕ close</span>'
            f'</div>'
            f'<div class="log-messages">{msg_items}</div>'
            f'</div></td></tr>'
        )
        return data_row + log_row

    rows = "".join(_row_pair(r) for r in records)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "repo": github_client.REPO_FULL_NAME,
        "s": s,
        "rows": rows,
    })


@app.on_event("startup")
def resume_watchers() -> None:
    """On startup, re-attach watchers for every session that was active when
    the process last stopped, and do a one-time sync for sessions that reached
    a terminal state while the app was down (so PR URLs are never missed)."""
    all_records = store.all_records()
    active = [r for r in all_records if r.get("session_id")
              and r.get("status") not in devin_client.TERMINAL_STATUSES]
    terminal_without_pr = [r for r in all_records if r.get("session_id")
                           and r.get("status") in devin_client.TERMINAL_STATUSES
                           and not r.get("pr_url")]

    for record in active:
        logger.info(
            "Resuming watcher for issue #%d (session_id=%s)",
            record["issue_number"], record["session_id"],
        )
        start_session_watcher(record["session_id"], record["issue_number"])

    for record in terminal_without_pr:
        logger.info(
            "Syncing terminal session for issue #%d (session_id=%s) — checking for PR",
            record["issue_number"], record["session_id"],
        )
        try:
            data = devin_client.get_session(record["session_id"])
            new_status, pr_url, pr_status = devin_client.extract_status_and_pr(data)
            status_detail = data.get("status_detail") or data.get("status_reason") or None
            messages = devin_client.get_session_messages(record["session_id"])
            num_user = sum(1 for m in messages if m.get("source") == "user")
            num_devin = sum(1 for m in messages if m.get("source") in ("assistant", "devin"))
            upsert_kwargs = dict(
                status=new_status,
                pr_url=pr_url or record.get("pr_url"),
                pr_status=pr_status,
                status_detail=status_detail,
                messages=messages,
                num_user_messages=num_user,
                num_devin_messages=num_devin,
            )
            insights = devin_client.get_session_insights(record["session_id"])
            if insights:
                upsert_kwargs.update(devin_client.extract_insights_fields(insights))
            store.upsert_record(record["issue_number"], **upsert_kwargs)
            if pr_url:
                logger.info(
                    "Recovered PR URL for issue #%d: %s",
                    record["issue_number"], pr_url,
                )
        except Exception:
            logger.error(
                "Failed to sync terminal session for issue #%d",
                record["issue_number"], exc_info=True,
            )


@app.get("/health")
def health():
    return {"ok": True}
