"""Schema-aligned prompt templates."""

import json
from typing import Any, Dict


def build_evidence_prompt(host: str, service: str, window_minutes: int, schema: Dict[str, Any]) -> str:
    return (
        "You are an SRE assistant. Collect evidence using read-only commands and return JSON that strictly "
        "matches the provided schema. Do not add extra keys.\n\n"
        f"Target host: {host}\n"
        f"Target service: {service}\n"
        f"Collection window: {window_minutes} minutes\n\n"
        "Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def build_report_prompt(evidence: Dict[str, Any], schema: Dict[str, Any]) -> str:
    return (
        "You are an SRE assistant. Generate a diagnosis report strictly following the provided JSON schema. "
        "Use the evidence pack and do not add extra keys.\n\n"
        f"Evidence pack:\n{json.dumps(evidence, ensure_ascii=False)}\n\n"
        "Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
