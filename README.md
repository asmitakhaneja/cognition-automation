# Devin × Superset Remediation Orchestrator

Event-driven automation that turns labeled GitHub issues on a fork of
[apache/superset](https://github.com/apache/superset) into Devin sessions,
which investigate the issue, write a fix + test, and open a pull request —
fully autonomously.

```
GitHub Issue labeled "devin-fix"
        │  (webhook)
        ▼
  Orchestrator (FastAPI)
        │  POST /v3/organizations/{org_id}/sessions
        ▼
     Devin session  ── investigates, fixes, tests, opens PR
        │
        ▼
  Orchestrator polls session status every 30s
        │
        ▼
  Dashboard (/) + JSON API (/status)
```

## Why a custom orchestrator instead of Devin's built-in "Automations"?

Devin's no-code Automations feature (the toggle in the Devin web app) is
scoped to private repositories as an abuse-prevention measure — a public
repo would let anyone open an issue and trigger a paid session on your
account. Since this project intentionally works against a public fork of
Superset, we integrate directly against the **Devin API** instead, with our
own GitHub webhook receiver as the trigger. This also better demonstrates
programmatic session management, which is the point of the exercise.

## Prerequisites

1. A Devin org with API access. Create a **service user** and API key
   (`cog_...`) — see [Devin API docs](https://docs.devin.ai/api-reference/overview).
2. Your Devin org connected to your forked GitHub repo (Devin Settings →
   Integrations → GitHub), with write access so it can push branches and
   open PRs.
3. A forked copy of `apache/superset` in your own GitHub org/account, with
   the issues you want remediated created and labeled `devin-fix`.
4. Docker + Docker Compose installed locally.
5. [ngrok](https://ngrok.com/) (or similar) if you want to receive live
   webhooks from a public GitHub repo while running locally.

## Setup

```bash
cp .env.example .env
# fill in DEVIN_API_KEY, DEVIN_ORG_ID, GITHUB_REPO, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET

docker compose up --build
```

The service starts on `http://localhost:8000`:
- `GET /` — live HTML dashboard
- `GET /status` — JSON status + summary metrics
- `POST /webhook/github` — GitHub webhook receiver
- `POST /trigger/{issue_number}` — manually trigger remediation for one issue
- `POST /trigger-all` — trigger remediation for every open issue labeled `devin-fix`
- `POST /session/{issue_number}/message?message=...` — send a follow-up instruction to a running session
- `GET /health` — liveness check

## Registering the GitHub webhook (for live event-driven triggering)

1. Expose your local server: `ngrok http 8000`, copy the `https://...ngrok-free.app` URL.
2. On your forked repo: **Settings → Webhooks → Add webhook**
   - Payload URL: `https://<your-ngrok-url>/webhook/github`
   - Content type: `application/json`
   - Secret: same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
   - Events: select **Issues** only
3. Label any issue `devin-fix` (or open a new issue with that label) — the
   webhook fires, the orchestrator creates a Devin session, and you'll see
   it appear on the dashboard within a few seconds.

If you'd rather not stand up a tunnel for the demo, use `POST /trigger-all`
or `POST /trigger/{issue_number}` to kick off the same flow manually — the
underlying Devin API integration is identical either way.

## Observability

The dashboard (`/`) and `/status` endpoint answer "is this working?" with:
- **Throughput**: total issues triggered, in progress, finished
- **Effectiveness**: PRs opened, success rate (% of triggered issues that produced a PR)
- **Speed**: average time from trigger to completion
- **Per-issue detail**: category tag, live status, direct links to the Devin session and the resulting PR

State is stored in a single JSON file (`/data/state.json`, mounted via
`docker-compose.yml`) — intentionally simple per the assignment's guidance;
swap in Postgres/SQLite for a production deployment without touching the
rest of the app.

## Project structure

```
app/
  main.py           FastAPI app: webhook, manual triggers, dashboard, poller
  devin_client.py   Devin v3 API wrapper (create session, poll, message, insights)
  github_client.py  GitHub REST API helper (fetch issue details)
  store.py          JSON-file state store + summary metrics
Dockerfile
docker-compose.yml
.env.example
```

## Notes on the 5 seeded issues

See the forked repo's issue tracker (labeled `devin-fix`) for the specific
security, dependency, code-quality, and test-coverage issues this system
was built to remediate, and the linked PRs Devin opened in response.
