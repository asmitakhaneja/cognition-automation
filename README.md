# cognition-automation

**[`devin-observability-dashboard/`](devin-observability-dashboard/)** — a single
application that combines two things:

1. **Observability dashboard** — progress, cost, adoption, and session logs
   from the Devin enterprise API, answering *"how would an engineering leader
   know this is working?"*
2. **Webhook automation** — a GitHub webhook receiver that turns `devin-fix`
   labeled issues on [`asmitakhaneja/superset`](https://github.com/asmitakhaneja/superset)
   into Devin sessions, and streams their live status/PRs into the dashboard's
   real-time **Automation** panel.

The webhook orchestrator and the dashboard are now one FastAPI service (with a
React/Vite frontend) that runs on built-in demo data with zero configuration.

## Quick start

```bash
cd devin-observability-dashboard
docker compose up --build      # http://localhost:8000
```

See [`devin-observability-dashboard/README.md`](devin-observability-dashboard/README.md)
for architecture, configuration, live-data setup, and the webhook wiring.
