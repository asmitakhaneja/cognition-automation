import requests
def build_prompt(issue):
    return f"""
You are fixing GitHub issue #{issue['number']} in {REPO_FULL_NAME}.

Title: {issue['title']}
Description: {issue['body']}

Instructions:
- Investigate the relevant code path before making changes.
- Make the minimal, correct fix — do not refactor unrelated code.
- Add or update a test that would have caught this issue.
- Run the existing test suite for the affected module and confirm it passes.
- Open a pull request against the `main` branch of this fork.
- Reference "Fixes #{issue['number']}" in the PR description.
""".strip()


def create_session(issue):
    resp = requests.post(
        f"https://api.devin.ai/v3/organizations/{ORG_ID}/sessions",
        headers={"Authorization": f"Bearer {DEVIN_API_KEY}"},
        json={
            "prompt": build_prompt(issue),
            "title": f"Fix #{issue['number']}: {issue['title']}",
            "tags": ["automation", categorize(issue)],  # e.g. "security", "deps", "quality", "tests"
        },
    )
    resp.raise_for_status()
    return resp.json()  # contains session_id, url