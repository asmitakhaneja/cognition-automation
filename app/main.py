import hashlib
import hmac
import json
import logging
import threading
import time
from urllib.parse import unquote_plus

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from . import store
from .client import devin_client, github_client
from .settings import (
    GITHUB_WEBHOOK_SECRET as WEBHOOK_SECRET,
    TRIGGER_LABEL,
    POLL_INTERVAL_SEC,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Devin x Superset Remediation Orchestrator")


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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    s = store.summary()
    records = store.all_records()

    rows = "".join(f"""
        <tr>
            <td>#{r['issue_number']}</td>
            <td>{r.get('title','')}</td>
            <td><span class="tag">{r.get('category','')}</span></td>
            <td class="status-{r.get('status','unknown')}">{r.get('status','unknown')}</td>
            <td>{f'<a href="{r["pr_url"]}" target="_blank">PR ↗</a>' if r.get('pr_url') else '—'}</td>
            <td>{f'<a href="{r["session_url"]}" target="_blank">session ↗</a>' if r.get('session_url') else '—'}</td>
        </tr>
    """ for r in records)

    return f"""
    <html>
    <head>
        <title>Devin Remediation Dashboard</title>
        <meta http-equiv="refresh" content="15">
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
            a {{ color: #60a5fa; text-decoration: none; }}
        </style>
    </head>
    <body>
        <h1>Devin Remediation Dashboard</h1>
        <p style="color:#94a3b8">Repo: {github_client.REPO_FULL_NAME} · Auto-refreshes every 15s</p>
        <div class="cards">
            <div class="card"><div class="num">{s['total_triggered']}</div><div class="label">Triggered</div></div>
            <div class="card"><div class="num">{s['in_progress']}</div><div class="label">In progress</div></div>
            <div class="card"><div class="num">{s['finished']}</div><div class="label">Finished</div></div>
            <div class="card"><div class="num">{s['prs_opened']}</div><div class="label">PRs opened</div></div>
            <div class="card"><div class="num">{s['blocked_or_failed']}</div><div class="label">Blocked/Failed</div></div>
            <div class="card"><div class="num">{s['success_rate_pct'] or '—'}%</div><div class="label">Success rate</div></div>
            <div class="card"><div class="num">{s['avg_time_to_finish_sec'] and int(s['avg_time_to_finish_sec']//60) or '—'}m</div><div class="label">Avg time to PR</div></div>
        </div>
        <table>
            <tr><th>Issue</th><th>Title</th><th>Category</th><th>Status</th><th>PR</th><th>Devin Session</th></tr>
            {rows or '<tr><td colspan="6" style="color:#64748b">No issues triggered yet.</td></tr>'}
        </table>
    </body>
    </html>
    """


# --------------------------------------------------------------------------
# Background poller: keeps session status / PR links up to date
# --------------------------------------------------------------------------
def poll_loop():
    while True:
        try:
            active = store.active_records()
            logger.debug("Polling %d active session(s)", len(active))
            for record in active:
                if not record.get("session_id"):
                    continue
                data = devin_client.get_session(record["session_id"])
                new_status, pr_url = devin_client.extract_status_and_pr(data)
                old_status = record.get("status")

                if new_status != old_status:
                    logger.info(
                        "Issue #%d status changed: %s -> %s",
                        record["issue_number"], old_status, new_status,
                    )
                if pr_url and not record.get("pr_url"):
                    logger.info(
                        "PR opened for issue #%d: %s",
                        record["issue_number"], pr_url,
                    )

                store.upsert_record(
                    record["issue_number"],
                    status=new_status,
                    pr_url=pr_url or record.get("pr_url"),
                )
        except Exception:
            logger.error("Poller encountered an error", exc_info=True)
        time.sleep(POLL_INTERVAL_SEC)


@app.on_event("startup")
def start_poller():
    logger.info("Starting background poller (interval=%ds)", POLL_INTERVAL_SEC)
    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"ok": True}
