"""Action policy filter.

Used to filter LLM-produced next_actions in the final report.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def filter_actions(
    actions: List[Dict[str, Any]],
    allowed_risks: List[str],
    deny_keywords: List[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    allowed: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    allowed_norm = [r.upper() for r in (allowed_risks or [])]
    deny_norm = [k.lower() for k in (deny_keywords or [])]

    for action in actions or []:
        risk = (action.get("risk") or "").upper()
        text = (action.get("action") or "").lower()
        reason = None
        if allowed_norm and risk not in allowed_norm:
            reason = "risk_not_allowed"
        elif any(k in text for k in deny_norm):
            reason = "deny_keyword"

        if reason:
            blocked.append({**action, "blocked_reason": reason})
        else:
            allowed.append(action)

    return allowed, blocked
