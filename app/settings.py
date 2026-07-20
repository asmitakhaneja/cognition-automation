import os
from dotenv import load_dotenv

load_dotenv()

# --- Required ---
DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
DEVIN_ORG_ID = os.environ["DEVIN_ORG_ID"]
GITHUB_REPO = os.environ["GITHUB_REPO"]  # e.g. "your-org/superset"

# --- Optional GitHub ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

# --- Optional app behaviour ---
TRIGGER_LABEL = os.environ.get("TRIGGER_LABEL", "devin-fix")
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "30"))
STORE_PATH = os.environ.get("STORE_PATH", "/data/state.json")

# --- Optional Devin session settings ---
BYPASS_APPROVAL: bool | None = os.environ.get("BYPASS_APPROVAL")
MAX_ACU_LIMIT: int | None = os.environ.get("MAX_ACU_LIMIT")
PLAYBOOK_ID: str | None = os.environ.get("PLAYBOOK_ID")
KNOWLEDGE_IDS: list[str] = [
    k for k in os.environ.get("KNOWLEDGE_IDS", "").split(",") if k
]
RESUMABLE: bool | None = os.environ.get("RESUMABLE")

if BYPASS_APPROVAL is not None:
    BYPASS_APPROVAL = BYPASS_APPROVAL.lower() == "true"
if MAX_ACU_LIMIT is not None:
    MAX_ACU_LIMIT = int(MAX_ACU_LIMIT)
if RESUMABLE is not None:
    RESUMABLE = RESUMABLE.lower() == "true"
