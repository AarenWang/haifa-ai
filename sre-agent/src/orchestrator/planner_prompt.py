"""Planner prompt builder for multi-round diagnose.

The planner is constrained to choose cmd_ids only from the provided allowlist.
It must return a JSON object that conforms to `schemas/plan_schema.json`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence


def build_plan_prompt(
    *,
    state: Dict[str, Any],
    allowed_cmd_pool: Sequence[str],
    plan_schema: Dict[str, Any],
    max_cmds_per_round: int,
) -> str:
    allowed = list(dict.fromkeys([c for c in (allowed_cmd_pool or []) if str(c).strip()]))
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    executed = state.get("executed_cmd_ids") if isinstance(state.get("executed_cmd_ids"), list) else []

    # Keep prompt compact: state contains only redacted summaries/signals.
    return (
        "You are an SRE diagnosis planner. Your job is to decide what evidence to collect next.\n"
        "Hard constraints:\n"
        "- You MUST return ONLY a single JSON object (no markdown, no code fences).\n"
        "- The JSON MUST conform to the provided plan schema (no extra keys).\n"
        "- You MUST ONLY choose cmd_id from allowed_cmd_pool (never invent cmd_id).\n"
        f"- You MUST propose at most {int(max_cmds_per_round)} cmd_id in next_cmds.\n"
        "- If evidence is sufficient, choose decision=STOP and explain stop_reason.\n\n"
        "Context (redacted summaries only):\n"
        f"state={json.dumps(state, ensure_ascii=False)}\n\n"
        f"allowed_cmd_pool={json.dumps(allowed, ensure_ascii=False)}\n"
        f"already_executed_cmd_ids={json.dumps(executed, ensure_ascii=False)}\n"
        f"budget={json.dumps(budget, ensure_ascii=False)}\n\n"
        "Plan schema:\n"
        f"{json.dumps(plan_schema, ensure_ascii=False)}\n"
    )
