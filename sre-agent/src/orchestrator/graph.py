"""Deterministic orchestrator.

This orchestrator keeps the "deterministic first" flow:
- discovery -> baseline -> classify -> targeted -> report

It uses the command registry + policy checks to execute read-only commands,
stores raw/redacted/parsed evidence, and produces an evidence_pack.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import sys

from policy.command_policy import is_command_allowed
from policy.validators import validate_pid, validate_service
from registry.commands import get_command_meta, render_command
from registry.parsers import parse_output
from registry.signals import extract_signals
from orchestrator.rules import RuleEngine
from storage.audit_store import AuditStore
from storage.evidence_store import EvidenceStore
from storage.redaction import hash_text, redact


LOG = logging.getLogger("sre_agent.orchestrator")


def _platform_auto(exec_mode: str) -> str:
    if exec_mode == "local":
        return "darwin" if sys.platform == "darwin" else "linux"
    return "linux"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OrchestratorContext:
    host: str
    service: str
    window_minutes: int = 30
    env: str = ""
    session_id: str = ""
    exec_mode: str = "ssh"  # ssh|local
    pid: Optional[str] = None
    platform: str = ""  # auto|linux|darwin|k8s


class Orchestrator:
    def __init__(self, config: Dict[str, Any], *, executor: Any) -> None:
        self.config = config
        self.executor = executor
        self.rule_engine = RuleEngine(config.get("rules", {}))

    def _resolve_platform(self, ctx: OrchestratorContext) -> str:
        platform = (ctx.platform or "auto").lower()
        if platform == "auto":
            platform = _platform_auto(ctx.exec_mode)
        return platform

    def exec_cmd(
        self,
        *,
        ctx: OrchestratorContext,
        cmd_id: str,
        platform: str,
        store: EvidenceStore,
        audit_store: Optional[AuditStore],
        commands_cfg: Dict[str, Any],
        allowed_risks: List[str],
        deny_keywords: List[str],
        pid: Optional[str] = None,
        service: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Execute one registered command and persist evidence.

        Returns (redacted_output, audit_id, signals_or_error).
        """
        meta = get_command_meta(commands_cfg, cmd_id)
        if not is_command_allowed(meta, allowed_risks, deny_keywords):
            return "", "", {"error": "blocked_by_policy"}

        cmd_platform = (meta.get("platform") or "").lower()
        if cmd_platform and cmd_platform not in ("any", "all") and cmd_platform != platform:
            return "", "", {"error": "platform_mismatch", "platform": platform, "cmd_platform": cmd_platform}

        template = meta.get("cmd")
        if "{service}" in template:
            _svc = service or ctx.service
            if not validate_service(_svc):
                return "", "", {"error": "invalid_service"}
        if "{pid}" in template:
            _pid = pid or ctx.pid or ""
            if not validate_pid(_pid):
                return "", "", {"error": "invalid_pid"}

        command = render_command(template, service=(service or ctx.service), pid=(pid or ctx.pid))

        started_at = now_iso()
        start_ts = time.time()
        output = self.executor.run(ctx.host, command, timeout=timeout)
        elapsed_ms = int((time.time() - start_ts) * 1000)

        redacted, redaction_rules, redacted_count = redact(output)
        output_hash = hash_text(redacted)

        audit_id = f"{cmd_id}-{int(start_ts)}"
        if audit_store is not None:
            audit_store.write(
                {
                    "session_id": ctx.session_id,
                    "id": audit_id,
                    "cmd_id": cmd_id,
                    "cmd": command,
                    "started_at": started_at,
                    "elapsed_ms": elapsed_ms,
                    "output_hash": output_hash,
                    "redacted_fields": redaction_rules,
                    "redacted_count": redacted_count,
                }
            )

        raw_ref = store.put_raw(cmd_id, output)
        redacted_ref = store.put_redacted(cmd_id, redacted)
        parsed = parse_output(cmd_id, redacted)
        parsed_ref = store.put_parsed(cmd_id, parsed)
        sig = extract_signals(parsed)
        store.write_index(
            f"event-{cmd_id}-{audit_id}",
            {
                "cmd_id": cmd_id,
                "raw_ref": raw_ref,
                "redacted_ref": redacted_ref,
                "parsed_ref": parsed_ref,
                "signals": sig.get("signals", {}),
                "timing": {"elapsed_ms": elapsed_ms, "timeout": False},
                "audit_ref": audit_id,
                "redaction": {"rules": redaction_rules, "replaced_count": redacted_count},
            },
        )
        return redacted, audit_id, sig.get("signals", {})

    def run(self, ctx: OrchestratorContext) -> Dict[str, Any]:
        LOG.info(
            "orchestrator start session_id=%s host=%s service=%s pid=%s exec_mode=%s platform=%s window_minutes=%s",
            ctx.session_id,
            ctx.host,
            ctx.service,
            ctx.pid,
            ctx.exec_mode,
            ctx.platform,
            ctx.window_minutes,
        )
        if not ctx.session_id:
            raise ValueError("session_id is required")

        if not validate_service(ctx.service):
            raise ValueError("invalid service")
        if ctx.pid is not None and ctx.pid != "" and not validate_pid(ctx.pid):
            raise ValueError("invalid pid")

        evidence_base_dir = self.config.get("evidence", {}).get("base_dir", "report")
        store = EvidenceStore(evidence_base_dir, ctx.session_id)

        audit_log = self.config.get("audit_log") or ""
        audit_store = AuditStore(audit_log) if audit_log else None

        policy = self.config.get("action_policy", {})
        allowed_risks = policy.get("allowed_risks", ["READ_ONLY"])
        deny_keywords = policy.get("deny_keywords", [])

        commands_cfg = self.config.get("commands", {})
        routes = (self.config.get("routes") or self.config.get("routing") or {}).get("routes", {})

        platform = self._resolve_platform(ctx)

        baseline_cfg = self.config.get("baseline", {})
        baseline_cmds_cfg = baseline_cfg.get("cmds")
        if isinstance(baseline_cmds_cfg, dict):
            baseline_cmds = list(baseline_cmds_cfg.get("any") or []) + list(baseline_cmds_cfg.get(platform) or [])
        else:
            baseline_cmds = baseline_cmds_cfg or [
                "uname",
                "uptime",
                "df",
            ]

        snapshots: List[Dict[str, Any]] = []
        audit_refs: List[str] = []
        all_signals: Dict[str, Any] = {}
        metrics: Dict[str, Any] = {"timeouts": 0, "empty_outputs": 0, "skipped": 0}

        for cmd_id in baseline_cmds:
            LOG.info("baseline exec cmd_id=%s", cmd_id)
            out, audit_ref, sig = self.exec_cmd(
                ctx=ctx,
                cmd_id=cmd_id,
                platform=platform,
                store=store,
                audit_store=audit_store,
                commands_cfg=commands_cfg,
                allowed_risks=allowed_risks,
                deny_keywords=deny_keywords,
                timeout=30,
            )
            if not audit_ref and not out:
                metrics["skipped"] += 1
            if not audit_ref:
                LOG.warning("baseline skipped cmd_id=%s", cmd_id)
                continue
            audit_refs.append(audit_ref)
            for k, v in (sig or {}).items():
                if v is not None:
                    all_signals[k] = v
            # lightweight snapshot summary
            first_line = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
            if not (out or "").strip():
                metrics["empty_outputs"] += 1
            snapshots.append(
                {
                    "cmd_id": cmd_id,
                    "signal": first_line[:200],
                    "summary": "collected",
                    "audit_ref": audit_ref,
                }
            )

        # classify (rule-based)
        hypotheses = self.rule_engine.classify(all_signals)
        for h in hypotheses:
            h["evidence_refs"] = audit_refs[:8]
        primary = hypotheses[0]["category"] if hypotheses else "UNKNOWN"
        LOG.info("classify primary=%s", primary)

        # targeted routing (deterministic)
        targeted_cmds = routes.get(primary, [])
        next_checks: List[Dict[str, str]] = []
        for cmd_id in targeted_cmds:
            if cmd_id in baseline_cmds:
                continue
            LOG.info("targeted exec cmd_id=%s", cmd_id)
            out, audit_ref, sig = self.exec_cmd(
                ctx=ctx,
                cmd_id=cmd_id,
                platform=platform,
                store=store,
                audit_store=audit_store,
                commands_cfg=commands_cfg,
                allowed_risks=allowed_risks,
                deny_keywords=deny_keywords,
                timeout=30,
            )
            if audit_ref:
                audit_refs.append(audit_ref)
                for k, v in (sig or {}).items():
                    if v is not None:
                        all_signals[k] = v
                first_line = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
                if not (out or "").strip():
                    metrics["empty_outputs"] += 1
                snapshots.append(
                    {
                        "cmd_id": cmd_id,
                        "signal": first_line[:200],
                        "summary": "targeted",
                        "audit_ref": audit_ref,
                    }
                )
            else:
                LOG.warning("targeted failed cmd_id=%s", cmd_id)
                next_checks.append({"cmd_id": cmd_id, "purpose": "blocked_or_failed"})

        # Re-run rules after targeted signals
        hypotheses = self.rule_engine.classify(all_signals)
        for h in hypotheses:
            h["evidence_refs"] = audit_refs[:8]
        primary = hypotheses[0]["category"] if hypotheses else primary
        LOG.info("reclassify primary=%s", primary)

        evidence_pack = {
            "meta": {
                "host": ctx.host,
                "service": ctx.service,
                "env": ctx.env,
                "session_id": ctx.session_id,
                "platform": platform,
                "timestamp": now_iso(),
            },
            "snapshots": snapshots,
            "hypothesis": hypotheses or [
                {
                    "category": primary,
                    "confidence": 0.2,
                    "why": "insufficient signals; fallback",
                    "evidence_refs": audit_refs[:8],
                }
            ],
            "next_checks": next_checks[:8],
            "signals": all_signals,
            "policy": {"allowed_risks": allowed_risks, "deny_keywords": deny_keywords},
            "metrics": metrics,
        }

        store.write_index("evidence_pack", evidence_pack)
        LOG.info(
            "orchestrator finished session_id=%s primary=%s baseline=%s targeted=%s",
            ctx.session_id,
            primary,
            len(baseline_cmds),
            len(targeted_cmds),
        )
        # Keep audit summary for offline replay (best-effort).
        if audit_store is not None:
            store.write_index(
                "audit_summary",
                {
                    "session_id": ctx.session_id,
                    "commands": [
                        {
                            "id": r.get("id", ""),
                            "cmd_id": r.get("cmd_id", ""),
                            "cmd": r.get("cmd", ""),
                            "started_at": r.get("started_at", ""),
                            "elapsed_ms": r.get("elapsed_ms", 0),
                            "output_hash": r.get("output_hash", ""),
                            "redacted_fields": r.get("redacted_fields", []),
                            "redacted_count": r.get("redacted_count", 0),
                        }
                        for r in audit_store.read_all()
                        if r.get("session_id") == ctx.session_id
                    ],
                },
            )
        return evidence_pack
