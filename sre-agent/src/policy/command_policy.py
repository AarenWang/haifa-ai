"""Command policy checks."""

from typing import Dict, List


def is_command_allowed(command_meta: Dict[str, str], allowed_risks: List[str], deny_keywords: List[str]) -> bool:
    risk = (command_meta.get("risk") or "").upper()
    cmd = (command_meta.get("cmd") or "").lower()

    if allowed_risks and risk not in [r.upper() for r in allowed_risks]:
        return False
    if any(keyword.lower() in cmd for keyword in deny_keywords):
        return False
    return True
