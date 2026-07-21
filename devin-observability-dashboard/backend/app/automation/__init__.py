"""Webhook-driven remediation orchestration.

Receives GitHub ``devin-fix`` issue events, launches Devin sessions to fix
them, and tracks each session's live status so the dashboard can render
real-time automation metrics.
"""
