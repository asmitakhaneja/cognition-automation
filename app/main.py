import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time
from urllib.parse import unquote_plus

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import store
from .client import devin_client, github_client
from .settings import (
    GITHUB_WEBHOOK_SECRET as WEBHOOK_SECRET,
    TRIGGER_LABEL,
    WATCHER_POLL_SEC,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Devin x Superset Remediation Orchestrator")


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
            num_user = sum(1 for m in messages if m.get("role") == "user")
            num_devin = sum(1 for m in messages if m.get("role") in ("assistant", "devin"))

            upsert_kwargs = dict(
                status=new_status,
                pr_url=pr_url or record.get("pr_url"),
                pr_status=pr_status,
                status_detail=status_detail,
                messages=messages,
                num_user_messages=num_user,
                num_devin_messages=num_devin,
            )

            # Fetch insights only when terminal (non-fatal)
            if new_status in devin_client.TERMINAL_STATUSES:
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
def dashboard():
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
        size = (r.get('session_size') or '').lower()
        size_html = (
            f'<span class="tag size-{size}">{size.upper()}</span> '
            if size else ''
        )
        intel = (
            f'{size_html}'
            f'H:{r.get("num_user_messages", "?")}'
            f'&thinsp;/&thinsp;D:{r.get("num_devin_messages", "?")}'
        )
        acus = r.get('acus_consumed')
        acus_html = str(round(float(acus), 1)) if acus is not None else '—'
        clf_conf = r.get('classification_confidence')
        conf_html = (
            f'<br><small class="detail">conf: {round(clf_conf, 2)}</small>'
            if clf_conf is not None else ''
        )

        msgs = r.get('messages') or []
        if msgs:
            msg_items = "".join(
                f'<div class="msg msg-{m.get("role","unknown")}">'
                f'<strong>{m.get("role","?")}</strong>: '
                f'{m.get("content","") or m.get("message","")}'
                f'</div>'
                for m in msgs
            )
        else:
            msg_items = '<em style="color:#64748b">No messages yet.</em>'

        data_row = f"""
        <tr data-issue="{n}" title="Click to toggle session log">
            <td>#{n}</td>
            <td>{r.get('title','')}</td>
            <td><span class="tag">{r.get('category','')}</span>{conf_html}{tools_html}</td>
            <td class="ts">{_relative_time(r.get('created_at'))}</td>
            <td class="status-{r.get('status','unknown')}">{r.get('status','unknown')}{detail_html}</td>
            <td>{f'<a href="{r["pr_url"]}" target="_blank">PR ↗</a>' if r.get('pr_url') else '—'}</td>
            <td><span class="tag pr-{r.get('pr_status','')}">{r.get('pr_status') or '—'}</span></td>
            <td class="ts">{acus_html}</td>
            <td class="ts">{intel}</td>
            <td>{f'<a href="{r["session_url"]}" target="_blank">session ↗</a>' if r.get('session_url') else '—'} ▶</td>
        </tr>"""
        log_row = f"""
        <tr id="log-{n}" style="display:none">
            <td colspan="10" class="log-cell">
                <div class="log-container">{msg_items}</div>
            </td>
        </tr>"""
        return data_row + log_row

    rows = "".join(_row_pair(r) for r in records)

    return f"""
    <html>
    <head>
        <title>Devin Remediation Dashboard</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
            h1 {{ font-weight: 600; }}
            .cards {{ display: flex; gap: 1rem; margin-bottom: 2rem; }}
            .card {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; min-width: 120px; }}
            .card .num {{ font-size: 1.8rem; font-weight: 700; }}
            .card .label {{ font-size: 0.8rem; color: #94a3b8; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ text-align: left; padding: 0.6rem; border-bottom: 1px solid #334155; }}
            th {{ color: #94a3b8; font-weight: 500; font-size: 0.8rem; text-transform: uppercase; }}
            .tag {{ background: #334155; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; }}
            .status-finished {{ color: #4ade80; }}
            .status-running {{ color: #facc15; }}
            .status-blocked, .status-expired, .status-stopped {{ color: #f87171; }}
            .ts {{ color: #94a3b8; font-size: 0.8rem; }}
            .detail {{ color: #94a3b8; font-size: 0.72rem; }}
            .tools {{ color: #64748b; font-size: 0.7rem; }}
            .pr-open {{ background: #14532d; color: #4ade80; }}
            .pr-merged {{ background: #3b0764; color: #c084fc; }}
            .pr-closed {{ background: #450a0a; color: #f87171; }}
            .size-s {{ background: #1e3a5f; color: #93c5fd; }}
            .size-m {{ background: #3b2810; color: #fbbf24; }}
            .size-l {{ background: #2d1b1b; color: #f87171; }}
            .log-cell {{ padding: 0 !important; }}
            .log-container {{ max-height: 280px; overflow-y: auto; background: #1e293b;
                              padding: 0.75rem; border-radius: 6px; font-size: 0.78rem; }}
            .msg {{ padding: 3px 8px; margin: 2px 0; border-radius: 4px; word-break: break-word; }}
            .msg-user {{ background: #1e3a5f; }}
            .msg-assistant, .msg-devin {{ background: #1a2e1a; }}
            tr[data-issue] {{ cursor: pointer; }}
            tr[data-issue]:hover td {{ background: #1e293b; }}
            a {{ color: #60a5fa; text-decoration: none; }}
        </style>
    </head>
    <body>
        <h1>Devin Remediation Dashboard</h1>
        <p style="color:#94a3b8">Repo: {github_client.REPO_FULL_NAME} · Updates in real-time</p>
        <div class="cards">
            <div class="card"><div class="num">{s['total_triggered']}</div><div class="label">Triggered</div></div>
            <div class="card"><div class="num">{s['in_progress']}</div><div class="label">In progress</div></div>
            <div class="card"><div class="num">{s['finished']}</div><div class="label">Finished</div></div>
            <div class="card"><div class="num">{s['prs_opened']}</div><div class="label">PRs opened</div></div>
            <div class="card"><div class="num">{s['prs_merged']}</div><div class="label">PRs merged</div></div>
            <div class="card"><div class="num">{s['blocked_or_failed']}</div><div class="label">Blocked/Failed</div></div>
            <div class="card"><div class="num">{s['success_rate_pct'] or '—'}%</div><div class="label">Success rate</div></div>
            <div class="card"><div class="num">{s['avg_time_to_finish_sec'] and int(s['avg_time_to_finish_sec']//60) or '—'}m</div><div class="label">Avg time to PR</div></div>
            <div class="card"><div class="num">{s['total_acus'] if s['total_acus'] is not None else '—'}</div><div class="label">Total ACUs</div></div>
            <div class="card"><div class="num">{s['avg_acus_per_fix'] if s['avg_acus_per_fix'] is not None else '—'}</div><div class="label">ACUs / fix</div></div>
        </div>
        <table>
            <tr><th>Issue</th><th>Title</th><th>Category</th><th>Started</th><th>Status</th><th>PR</th><th>PR Status</th><th>ACUs</th><th>Intel</th><th>Devin Session</th></tr>
            {rows or '<tr><td colspan="10" style="color:#64748b">No issues triggered yet.</td></tr>'}
        </table>
        <script>
            const es = new EventSource('/events');
            es.onmessage = () => location.reload();
            es.onerror = () => setTimeout(() => location.reload(), 5000);

            document.querySelectorAll('tr[data-issue]').forEach(row => {{
                row.addEventListener('click', () => {{
                    const log = document.getElementById('log-' + row.dataset.issue);
                    if (!log) return;
                    log.style.display = log.style.display === 'none' ? 'table-row' : 'none';
                }});
            }});
        </script>
    </body>
    </html>
    """


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
            num_user = sum(1 for m in messages if m.get("role") == "user")
            num_devin = sum(1 for m in messages if m.get("role") in ("assistant", "devin"))
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
