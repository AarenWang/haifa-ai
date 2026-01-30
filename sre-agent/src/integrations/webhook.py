"""Webhook integration for alert/ticket ingestion.

This is a minimal adapter that normalizes incoming payloads into the agent's
run context.
"""

from __future__ import annotations

from typing import Any, Dict


def normalize_alert(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Support common keys: host/service/env/window
    host = payload.get("host") or payload.get("hostname") or payload.get("instance") or ""
    service = payload.get("service") or payload.get("app") or payload.get("job") or ""
    env = payload.get("env") or payload.get("environment") or ""
    window = payload.get("window_minutes") or payload.get("window") or 30
    try:
        window = int(window)
    except Exception:
        window = 30

    return {"host": str(host), "service": str(service), "env": str(env), "window_minutes": window}


def build_ticket_payload(report: Dict[str, Any]) -> Dict[str, Any]:
    """Convert report schema output to a generic ticket payload."""
    meta = report.get("meta") or {}
    rc = report.get("root_cause") or {}
    return {
        "title": f"SRE diagnosis: {meta.get('service','')} on {meta.get('host','')}",
        "severity": "info",
        "labels": ["sre-agent", str(rc.get("category") or "UNKNOWN").lower()],
        "summary": rc.get("summary") or "",
        "details": report,
    }
