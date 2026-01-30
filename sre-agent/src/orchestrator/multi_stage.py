"""Multi-round diagnosis loop (routing-restricted).

Design goals:
- Deterministic-first baseline collection (reuse existing Orchestrator)
- LLM produces a plan JSON; system executes cmd_ids (no direct tool-calling)
- LLM cmd selection is restricted to routing.yaml pool (for primary category)
- Full audit + redaction + evidence store integration
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from adapters.llm.base import LLMClient
from orchestrator.graph import Orchestrator, OrchestratorContext
from orchestrator.planner_prompt import build_plan_prompt
from reporting.schema_validate import validate_schema
from registry.commands import get_command_meta


LOG = logging.getLogger("sre_agent.orchestrator.multi_stage")


@dataclass(frozen=True)
class DiagnoseBudget:
    max_rounds: int = 3
    max_cmds_per_round: int = 3
    max_total_cmds: int = 12
    time_budget_sec: int = 120
    confidence_threshold: float = 0.85


def _load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"invalid json object: {path}")
    return data


def _primary_category(evidence_pack: Dict[str, Any]) -> str:
    hyp = evidence_pack.get("hypothesis")
    if isinstance(hyp, list) and hyp:
        top = hyp[0]
        if isinstance(top, dict) and top.get("category"):
            return str(top.get("category"))
    return "UNKNOWN"


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _as_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _get_allowed_cmd_pool(config: Dict[str, Any], primary: str) -> List[str]:
    routes_root = (config.get("routes") or config.get("routing") or {}).get("routes", {})
    pool = routes_root.get(primary) or []
    if not isinstance(pool, list):
        return []
    return [str(x) for x in pool if str(x).strip()]


def _filter_plan_cmds(
    *,
    plan: Dict[str, Any],
    allowed_pool: Sequence[str],
    already_executed: Set[str],
    commands_cfg: Dict[str, Any],
    max_cmds_per_round: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    allowed_set = set([str(x) for x in allowed_pool])
    proposed = plan.get("next_cmds")
    if not isinstance(proposed, list):
        proposed = []

    kept: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    for item in proposed:
        if not isinstance(item, dict):
            continue
        cmd_id = str(item.get("cmd_id") or "").strip()
        if not cmd_id:
            continue
        if cmd_id not in allowed_set:
            blocked.append({"cmd_id": cmd_id, "reason": "not_in_allowed_pool"})
            continue
        if cmd_id in already_executed:
            blocked.append({"cmd_id": cmd_id, "reason": "duplicate"})
            continue
        try:
            _ = get_command_meta(commands_cfg, cmd_id)
        except Exception:
            blocked.append({"cmd_id": cmd_id, "reason": "unknown_cmd_id"})
            continue
        kept.append(item)
        if len(kept) >= int(max_cmds_per_round):
            break
    return kept, blocked


def multi_round_diagnose(
    *,
    config: Dict[str, Any],
    ctx: OrchestratorContext,
    executor: Any,
    llm: LLMClient,
    plan_schema_path: str,
    report_schema_path: str,
    budget: DiagnoseBudget,
) -> Dict[str, Any]:
    """Run baseline collection then multi-round LLM planning loop.

    Returns a dict containing:
    - evidence_pack
    - diagnosis_report
    - diagnosis_trace
    """
    plan_schema = _load_json_file(plan_schema_path)
    report_schema = _load_json_file(report_schema_path)

    # Step 1: baseline + deterministic targeted collection (existing behavior)
    orch = Orchestrator(config, executor=executor)
    evidence_pack = orch.run(ctx)
    primary = _primary_category(evidence_pack)
    initial_primary = primary

    allowed_pool = _get_allowed_cmd_pool(config, primary)
    commands_cfg = config.get("commands", {})

    trace_rounds: List[Dict[str, Any]] = []
    executed_cmd_ids: Set[str] = set(
        [s.get("cmd_id") for s in (evidence_pack.get("snapshots") or []) if isinstance(s, dict) and s.get("cmd_id")]
    )
    total_cmds_before = len(executed_cmd_ids)

    start_ts = time.time()
    stop_reason = ""

    # Evidence store base dir is used by Orchestrator already; keep trace in same session index.
    evidence_base_dir = config.get("evidence", {}).get("base_dir", "report")
    from storage.evidence_store import EvidenceStore

    store = EvidenceStore(evidence_base_dir, ctx.session_id)

    audit_log = config.get("audit_log") or ""
    from storage.audit_store import AuditStore

    audit_store = AuditStore(audit_log) if audit_log else None

    policy = config.get("action_policy", {})
    allowed_risks = policy.get("allowed_risks", ["READ_ONLY"])
    deny_keywords = policy.get("deny_keywords", [])

    platform = orch._resolve_platform(ctx)

    for round_idx in range(1, int(budget.max_rounds) + 1):
        elapsed = int(time.time() - start_ts)
        if elapsed >= int(budget.time_budget_sec):
            stop_reason = "time_budget_exceeded"
            break
        if len(executed_cmd_ids) - total_cmds_before >= int(budget.max_total_cmds):
            stop_reason = "max_total_cmds_exceeded"
            break

        remaining_pool = [c for c in allowed_pool if c not in executed_cmd_ids]
        if not remaining_pool:
            stop_reason = "allowed_cmd_pool_exhausted"
            break

        # Build compact state for LLM: only summaries + signals, no raw.
        state = {
            "meta": evidence_pack.get("meta", {}),
            "primary_category": primary,
            "hypothesis": evidence_pack.get("hypothesis", []),
            "signals": evidence_pack.get("signals", {}),
            "snapshots": evidence_pack.get("snapshots", [])[-20:],
            "executed_cmd_ids": sorted(list(executed_cmd_ids)),
            "budget": {
                "round": round_idx,
                "max_rounds": int(budget.max_rounds),
                "max_cmds_per_round": int(budget.max_cmds_per_round),
                "max_total_cmds": int(budget.max_total_cmds),
                "time_budget_sec": int(budget.time_budget_sec),
                "confidence_threshold": float(budget.confidence_threshold),
            },
        }

        prompt = build_plan_prompt(
            state=state,
            allowed_cmd_pool=remaining_pool,
            plan_schema=plan_schema,
            max_cmds_per_round=int(budget.max_cmds_per_round),
        )

        LOG.info("llm plan round=%s primary=%s remaining_pool=%s", round_idx, primary, len(remaining_pool))
        plan = llm.generate_json(prompt, plan_schema, temperature=0.2)
        validate_schema(plan, plan_schema)

        decision = str(plan.get("decision") or "").upper()
        # Early stop by LLM
        if decision == "STOP":
            stop_reason = str(plan.get("stop_reason") or "llm_stop")
            trace_rounds.append(
                {
                    "round": round_idx,
                    "decision": "STOP",
                    "plan": plan,
                    "allowed_cmd_pool": remaining_pool,
                    "blocked": [],
                    "executed": [],
                }
            )
            break

        kept, blocked = _filter_plan_cmds(
            plan=plan,
            allowed_pool=remaining_pool,
            already_executed=executed_cmd_ids,
            commands_cfg=commands_cfg,
            max_cmds_per_round=int(budget.max_cmds_per_round),
        )

        executed: List[Dict[str, Any]] = []
        for item in kept:
            cmd_id = str(item.get("cmd_id"))
            timeout_sec = _as_int(item.get("timeout_sec"), 30)
            out, audit_ref, sig = orch.exec_cmd(
                ctx=ctx,
                cmd_id=cmd_id,
                platform=platform,
                store=store,
                audit_store=audit_store,
                commands_cfg=commands_cfg,
                allowed_risks=allowed_risks,
                deny_keywords=deny_keywords,
                timeout=timeout_sec,
            )

            # Merge into evidence_pack snapshots/signals
            if audit_ref:
                evidence_pack.setdefault("snapshots", [])
                first_line = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
                evidence_pack["snapshots"].append(
                    {
                        "cmd_id": cmd_id,
                        "signal": first_line[:200],
                        "summary": f"round_{round_idx}",
                        "audit_ref": audit_ref,
                    }
                )
            if isinstance(sig, dict):
                evidence_pack.setdefault("signals", {})
                for k, v in sig.items():
                    if v is not None:
                        evidence_pack["signals"][k] = v

            executed_cmd_ids.add(cmd_id)
            executed.append({"cmd_id": cmd_id, "timeout_sec": timeout_sec, "audit_ref": audit_ref})

        # Update hypothesis after new evidence using existing rule engine
        if isinstance(evidence_pack.get("signals"), dict):
            from orchestrator.rules import RuleEngine

            re = RuleEngine(config.get("rules", {}))
            hypotheses = re.classify(evidence_pack.get("signals") or {})
            evidence_pack["hypothesis"] = hypotheses
            primary = _primary_category(evidence_pack)

        trace_rounds.append(
            {
                "round": round_idx,
                "decision": decision or "CONTINUE",
                "plan": plan,
                "allowed_cmd_pool": remaining_pool,
                "blocked": blocked,
                "executed": executed,
            }
        )

        # Persist per-round trace
        store.write_index(f"llm_round_{round_idx:03d}", trace_rounds[-1])

        # Confidence early stop
        try:
            hyp0 = (evidence_pack.get("hypothesis") or [])[0]
            conf = _as_float(hyp0.get("confidence"), 0.0) if isinstance(hyp0, dict) else 0.0
            if conf >= float(budget.confidence_threshold):
                stop_reason = "confidence_threshold_reached"
                break
        except Exception:
            pass

    if not stop_reason:
        stop_reason = "max_rounds_reached"

    # Final report
    from reporting.report_builder import build_report

    evidence_pack.setdefault("meta", {})
    # add minimal fields expected by report schema meta if missing
    if isinstance(evidence_pack.get("meta"), dict):
        evidence_pack["meta"].setdefault("collection_window_minutes", ctx.window_minutes)
        evidence_pack["meta"].setdefault("agent_version", "dev")

    report = build_report(llm, evidence_pack, report_schema)
    validate_schema(report, report_schema)

    diagnosis_trace = {
        "session_id": ctx.session_id,
        "initial_primary": initial_primary,
        "primary": _primary_category(evidence_pack),
        "stop_reason": stop_reason,
        "budget": {
            "max_rounds": int(budget.max_rounds),
            "max_cmds_per_round": int(budget.max_cmds_per_round),
            "max_total_cmds": int(budget.max_total_cmds),
            "time_budget_sec": int(budget.time_budget_sec),
            "confidence_threshold": float(budget.confidence_threshold),
        },
        "rounds": trace_rounds,
    }

    store.write_index("diagnosis_trace", diagnosis_trace)
    store.write_index("diagnosis_report", report)
    store.write_index("evidence_pack", evidence_pack)

    return {"evidence_pack": evidence_pack, "diagnosis_report": report, "diagnosis_trace": diagnosis_trace}
