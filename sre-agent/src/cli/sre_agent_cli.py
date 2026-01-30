"""SRE Agent CLI (first runnable slice).

Config switching example:
  export SRE_LLM_VENDOR=qwen
  export SRE_AGENT_SDK_VENDOR=claude_sdk

Run a command:
  python -m src.cli.sre_agent_cli exec --host 1.2.3.4 --cmd-id uptime
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict

# Ensure src/ is on sys.path when running as a script
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from adapters.llm.base import create_llm_client  # noqa: E402
from adapters.agent_sdk.base import create_agent_sdk_client  # noqa: E402
from adapters.exec.ssh import SSHExecutor  # noqa: E402
from adapters.exec.local import LocalExecutor  # noqa: E402
from config import load_configs, apply_env_overrides  # noqa: E402
from policy.command_policy import is_command_allowed  # noqa: E402
from policy.validators import validate_pid, validate_service  # noqa: E402
from registry.commands import get_command_meta, load_commands, render_command  # noqa: E402
from storage.audit_store import AuditStore  # noqa: E402
from storage.redaction import hash_text, redact  # noqa: E402
from reporting.report_builder import build_report  # noqa: E402
from reporting.schema_validate import validate_schema  # noqa: E402
from orchestrator.graph import Orchestrator, OrchestratorContext  # noqa: E402
from orchestrator.multi_stage import DiagnoseBudget, multi_round_diagnose  # noqa: E402
from integrations.webhook import normalize_alert  # noqa: E402
from integrations.webhook import build_ticket_payload  # noqa: E402


LOG = logging.getLogger("sre_agent")


def configure_logging(level: str) -> None:
    """Configure logging to stdout for CLI runs."""
    lvl = (level or "INFO").upper()
    numeric = getattr(logging, lvl, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )


def load_runtime_env() -> Dict[str, Any]:
    return {
        "llm_vendor": os.getenv("SRE_LLM_VENDOR"),
        "agent_sdk_vendor": os.getenv("SRE_AGENT_SDK_VENDOR"),
        "llm": {"model": os.getenv("SRE_LLM_MODEL")},
        "agent_sdk": {"mode": os.getenv("SRE_AGENT_SDK_MODE")},
        "ssh": {
            "user": os.getenv("SRE_SSH_USER"),
            "password": os.getenv("SRE_SSH_PASSWORD"),
            "port": os.getenv("SRE_SSH_PORT"),
        },
        "audit_log": os.getenv("OPS_AGENT_AUDIT_LOG"),
    }


def merge_env_config(config: Dict[str, Any], env_cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(config)
    for key, value in env_cfg.items():
        if isinstance(value, dict):
            merged[key] = {**merged.get(key, {}), **{k: v for k, v in value.items() if v}}
        elif value:
            merged[key] = value
    return merged


def build_config_paths(config_dir: str) -> Dict[str, str]:
    return {
        "policy": os.path.join(config_dir, "policy.yaml"),
        "commands": os.path.join(config_dir, "commands.yaml"),
        "routing": os.path.join(config_dir, "routing.yaml"),
        "runtime": os.path.join(config_dir, "runtime.yaml"),
        "rules": os.path.join(config_dir, "rules.yaml"),
    }


def handle_exec(args: argparse.Namespace) -> int:
    LOG.info("exec start host=%s cmd_id=%s exec_mode=%s", args.host, args.cmd_id, args.exec_mode)
    config_paths = build_config_paths(args.config_dir)
    base_cfg = load_configs([config_paths["runtime"], config_paths["policy"], config_paths["commands"], config_paths["rules"]])
    base_cfg = apply_env_overrides(base_cfg)
    cfg = merge_env_config(base_cfg, load_runtime_env())

    commands_cfg = load_commands(cfg)
    try:
        meta = get_command_meta(commands_cfg, args.cmd_id)
    except Exception as exc:
        LOG.error("exec command not found cmd_id=%s err=%s", args.cmd_id, exc)
        print(f"command not found: {exc}")
        return 2

    policy = cfg.get("action_policy", {})
    allowed_risks = policy.get("allowed_risks", ["READ_ONLY"])
    deny_keywords = policy.get("deny_keywords", [])
    if not is_command_allowed(meta, allowed_risks, deny_keywords):
        LOG.warning("exec blocked by policy cmd_id=%s", args.cmd_id)
        print("command blocked by policy")
        return 3

    template = meta.get("cmd")
    if "{service}" in template and not validate_service(args.service or ""):
        LOG.error("exec invalid service cmd_id=%s", args.cmd_id)
        print("invalid or missing --service")
        return 4
    if "{pid}" in template and not validate_pid(args.pid or ""):
        LOG.error("exec invalid pid cmd_id=%s", args.cmd_id)
        print("invalid or missing --pid")
        return 4

    try:
        command = render_command(template, service=args.service, pid=args.pid)
    except Exception as exc:
        LOG.exception("exec failed to render cmd_id=%s", args.cmd_id)
        print(f"failed to render command: {exc}")
        return 5

    exec_mode = (args.exec_mode or "ssh").lower()
    if exec_mode not in ("ssh", "local"):
        LOG.error("exec invalid exec_mode=%s", exec_mode)
        print("invalid --exec-mode (use ssh|local)")
        return 6

    executor = None
    if exec_mode == "local":
        executor = LocalExecutor({})
    else:
        ssh_cfg = cfg.get("ssh", {})
        if args.ssh_user:
            ssh_cfg["user"] = args.ssh_user
        if args.ssh_password:
            ssh_cfg["password"] = args.ssh_password
        if args.ssh_port:
            ssh_cfg["port"] = str(args.ssh_port)
        executor = SSHExecutor(ssh_cfg)

    import time
    from datetime import datetime, timezone

    started_at = datetime.now(timezone.utc).isoformat()
    start_ts = time.time()
    output = executor.run(args.host, command, timeout=args.timeout)
    elapsed_ms = int((time.time() - start_ts) * 1000)
    LOG.info("exec finished cmd_id=%s elapsed_ms=%s", args.cmd_id, elapsed_ms)

    redacted, rules, replaced = redact(output)
    output_hash = hash_text(redacted)

    audit_log = args.audit_log or cfg.get("audit_log") or ""
    if audit_log:
        record = {
            "id": f"{args.cmd_id}-{int(start_ts)}",
            "cmd_id": args.cmd_id,
            "cmd": command,
            "started_at": started_at,
            "elapsed_ms": elapsed_ms,
            "output_hash": output_hash,
            "redacted_fields": rules,
            "redacted_count": replaced,
        }
        AuditStore(audit_log).write(record)

    print(redacted)
    return 0


def handle_info(args: argparse.Namespace) -> int:
    config_paths = build_config_paths(args.config_dir)
    cfg = apply_env_overrides(load_configs([config_paths["runtime"], config_paths["rules"]]))
    cfg = merge_env_config(cfg, load_runtime_env())

    llm_vendor = args.llm_vendor or cfg.get("llm_vendor", "qwen")
    sdk_vendor = args.agent_sdk_vendor or cfg.get("agent_sdk_vendor", "claude_sdk")

    _llm = create_llm_client(llm_vendor, cfg.get("llm", {}))
    _sdk = create_agent_sdk_client(sdk_vendor, cfg.get("agent_sdk", {}))

    LOG.info("info llm_vendor=%s agent_sdk_vendor=%s", llm_vendor, sdk_vendor)

    print(f"LLM vendor: {llm_vendor} capabilities={_llm.capabilities()}")
    print(f"Agent SDK: {sdk_vendor} capabilities={_sdk.capabilities()}")
    return 0


def handle_report(args: argparse.Namespace) -> int:
    LOG.info("report start evidence=%s schema=%s", args.evidence, args.schema)
    config_paths = build_config_paths(args.config_dir)
    cfg = apply_env_overrides(load_configs([config_paths["runtime"], config_paths["policy"]]))
    cfg = merge_env_config(cfg, load_runtime_env())

    llm_vendor = args.llm_vendor or cfg.get("llm_vendor", "qwen")
    _llm = create_llm_client(llm_vendor, cfg.get("llm", {}))

    with open(args.evidence, "r", encoding="utf-8") as f:
        evidence = json.load(f)
    with open(args.schema, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Pass policy into evidence so report builder can enforce it.
    if isinstance(evidence, dict):
        evidence.setdefault("policy", cfg.get("action_policy", {}))
    report = build_report(_llm, evidence, schema)
    LOG.info("report finished")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def handle_run(args: argparse.Namespace) -> int:
    LOG.info(
        "run start host=%s service=%s pid=%s exec_mode=%s window_minutes=%s",
        args.host,
        args.service,
        args.pid,
        args.exec_mode,
        args.window_minutes,
    )
    config_paths = build_config_paths(args.config_dir)
    base_cfg = load_configs(
        [
            config_paths["runtime"],
            config_paths["policy"],
            config_paths["commands"],
            config_paths["routing"],
            config_paths["rules"],
        ]
    )
    base_cfg = apply_env_overrides(base_cfg)
    cfg = merge_env_config(base_cfg, load_runtime_env())

    exec_mode = (args.exec_mode or "ssh").lower()
    if exec_mode not in ("ssh", "local"):
        LOG.error("run invalid exec_mode=%s", exec_mode)
        print("invalid --exec-mode (use ssh|local)")
        return 6

    if exec_mode == "local":
        executor = LocalExecutor({})
    else:
        ssh_cfg = cfg.get("ssh", {})
        if args.ssh_user:
            ssh_cfg["user"] = args.ssh_user
        if args.ssh_password:
            ssh_cfg["password"] = args.ssh_password
        if args.ssh_port:
            ssh_cfg["port"] = str(args.ssh_port)
        executor = SSHExecutor(ssh_cfg)

    # session id: deterministic enough for local usage
    from datetime import datetime

    session_id = args.session_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    orch = Orchestrator(cfg, executor=executor)
    ctx = OrchestratorContext(
        host=args.host,
        service=args.service,
        window_minutes=args.window_minutes,
        env=args.env or "",
        session_id=session_id,
        exec_mode=exec_mode,
        pid=args.pid,
        platform=args.platform,
    )

    evidence_pack = orch.run(ctx)
    LOG.info("run finished session_id=%s", session_id)
    schema_path = args.evidence_schema
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    validate_schema(evidence_pack, schema)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(evidence_pack, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(evidence_pack, ensure_ascii=False, indent=2))
    return 0


def handle_diagnose(args: argparse.Namespace) -> int:
    config_paths = build_config_paths(args.config_dir)
    base_cfg = load_configs(
        [
            config_paths["runtime"],
            config_paths["policy"],
            config_paths["commands"],
            config_paths["routing"],
            config_paths["rules"],
        ]
    )
    base_cfg = apply_env_overrides(base_cfg)
    cfg = merge_env_config(base_cfg, load_runtime_env())

    exec_mode = (args.exec_mode or "ssh").lower()
    if exec_mode not in ("ssh", "local"):
        LOG.error("diagnose invalid exec_mode=%s", exec_mode)
        print("invalid --exec-mode (use ssh|local)")
        return 6

    if exec_mode == "local":
        executor = LocalExecutor({})
    else:
        ssh_cfg = cfg.get("ssh", {})
        if args.ssh_user:
            ssh_cfg["user"] = args.ssh_user
        if args.ssh_password:
            ssh_cfg["password"] = args.ssh_password
        if args.ssh_port:
            ssh_cfg["port"] = str(args.ssh_port)
        executor = SSHExecutor(ssh_cfg)

    from datetime import datetime

    session_id = args.session_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    llm_vendor = args.llm_vendor or cfg.get("llm_vendor", "qwen")
    llm = create_llm_client(llm_vendor, cfg.get("llm", {}))

    ctx = OrchestratorContext(
        host=args.host,
        service=args.service,
        window_minutes=args.window_minutes,
        env=args.env or "",
        session_id=session_id,
        exec_mode=exec_mode,
        pid=args.pid,
        platform=args.platform,
    )

    budget = DiagnoseBudget(
        max_rounds=args.max_rounds,
        max_cmds_per_round=args.max_cmds_per_round,
        max_total_cmds=args.max_total_cmds,
        time_budget_sec=args.time_budget_sec,
        confidence_threshold=args.confidence_threshold,
    )

    LOG.info(
        "diagnose start host=%s service=%s pid=%s exec_mode=%s platform=%s session_id=%s llm=%s",
        args.host,
        args.service,
        args.pid,
        exec_mode,
        args.platform,
        session_id,
        llm_vendor,
    )

    result = multi_round_diagnose(
        config=cfg,
        ctx=ctx,
        executor=executor,
        llm=llm,
        plan_schema_path=args.plan_schema,
        report_schema_path=args.report_schema,
        budget=budget,
    )

    def _ensure_parent(path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    if args.output_evidence:
        _ensure_parent(args.output_evidence)
        with open(args.output_evidence, "w", encoding="utf-8") as f:
            json.dump(result["evidence_pack"], f, ensure_ascii=False, indent=2)
    if args.output_report:
        _ensure_parent(args.output_report)
        with open(args.output_report, "w", encoding="utf-8") as f:
            json.dump(result["diagnosis_report"], f, ensure_ascii=False, indent=2)
    if args.output_trace:
        _ensure_parent(args.output_trace)
        with open(args.output_trace, "w", encoding="utf-8") as f:
            json.dump(result["diagnosis_trace"], f, ensure_ascii=False, indent=2)

    session_dir = os.path.abspath(os.path.join(cfg.get("evidence", {}).get("base_dir", "report"), session_id))
    LOG.info(
        "diagnose outputs evidence=%s report=%s trace=%s session_dir=%s",
        os.path.abspath(args.output_evidence) if args.output_evidence else "",
        os.path.abspath(args.output_report) if args.output_report else "",
        os.path.abspath(args.output_trace) if args.output_trace else "",
        session_dir,
    )

    # Default to printing report if no output file is specified
    if not args.output_report:
        print(json.dumps(result["diagnosis_report"], ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="SRE Agent CLI")
    ap.add_argument("--config-dir", default="configs")
    ap.add_argument("--log-level", default=os.getenv("SRE_LOG_LEVEL", "INFO"))

    sub = ap.add_subparsers(dest="command")

    info = sub.add_parser("info", help="show llm/sdk selection")
    info.add_argument("--llm-vendor", default=None)
    info.add_argument("--agent-sdk-vendor", default=None)

    exe = sub.add_parser("exec", help="execute a read-only command by cmd_id")
    exe.add_argument("--host", required=True)
    exe.add_argument("--cmd-id", required=True)
    exe.add_argument("--service", default=None)
    exe.add_argument("--pid", default=None)
    exe.add_argument("--timeout", type=int, default=30)
    exe.add_argument("--exec-mode", default="ssh")
    exe.add_argument("--ssh-user", default=None)
    exe.add_argument("--ssh-password", default=None)
    exe.add_argument("--ssh-port", type=int, default=None)
    exe.add_argument("--audit-log", default=None)

    rep = sub.add_parser("report", help="generate report from evidence + schema via LLM")
    rep.add_argument("--evidence", required=True)
    rep.add_argument("--schema", required=True)
    rep.add_argument("--llm-vendor", default=None)

    run = sub.add_parser("run", help="run orchestrator to collect evidence pack")
    run.add_argument("--host", required=True)
    run.add_argument("--service", required=True)
    run.add_argument("--window-minutes", type=int, default=30)
    run.add_argument("--env", default="")
    run.add_argument("--pid", default=None)
    run.add_argument("--platform", default="auto", help="auto|linux|darwin|k8s")
    run.add_argument("--session-id", default=None)
    run.add_argument("--exec-mode", default="ssh")
    run.add_argument("--ssh-user", default=None)
    run.add_argument("--ssh-password", default=None)
    run.add_argument("--ssh-port", type=int, default=None)
    run.add_argument("--evidence-schema", default=os.path.join("schemas", "evidence_schema.json"))
    run.add_argument("--output", default=None)

    diag = sub.add_parser("diagnose", help="multi-round diagnose (collect + plan + report)")
    diag.add_argument("--host", required=True)
    diag.add_argument("--service", required=True)
    diag.add_argument("--window-minutes", type=int, default=30)
    diag.add_argument("--env", default="")
    diag.add_argument("--pid", default=None)
    diag.add_argument("--platform", default="auto", help="auto|linux|darwin|k8s")
    diag.add_argument("--session-id", default=None)
    diag.add_argument("--exec-mode", default="ssh")
    diag.add_argument("--ssh-user", default=None)
    diag.add_argument("--ssh-password", default=None)
    diag.add_argument("--ssh-port", type=int, default=None)
    diag.add_argument("--llm-vendor", default=None)
    diag.add_argument("--plan-schema", default=os.path.join("schemas", "plan_schema.json"))
    diag.add_argument("--report-schema", default=os.path.join("schemas", "report_schema.json"))
    diag.add_argument("--max-rounds", type=int, default=3)
    diag.add_argument("--max-cmds-per-round", type=int, default=3)
    diag.add_argument("--max-total-cmds", type=int, default=12)
    diag.add_argument("--time-budget-sec", type=int, default=120)
    diag.add_argument("--confidence-threshold", type=float, default=0.85)
    diag.add_argument("--output-evidence", default=os.path.join("report", "evidence_pack.json"))
    diag.add_argument("--output-report", default=os.path.join("report", "report.json"))
    diag.add_argument("--output-trace", default=os.path.join("report", "diagnosis_trace.json"))

    alert = sub.add_parser("ingest-alert", help="normalize an alert payload to run args")
    alert.add_argument("--payload", required=True, help="path to JSON payload")

    ticket = sub.add_parser("ticket", help="convert report json to ticket payload")
    ticket.add_argument("--report", required=True, help="path to report json")

    args = ap.parse_args()

    configure_logging(args.log_level)

    if args.command == "exec":
        raise SystemExit(handle_exec(args))
    if args.command == "report":
        raise SystemExit(handle_report(args))
    if args.command == "run":
        raise SystemExit(handle_run(args))
    if args.command == "diagnose":
        raise SystemExit(handle_diagnose(args))
    if args.command == "ingest-alert":
        with open(args.payload, "r", encoding="utf-8") as f:
            payload = json.load(f)
        norm = normalize_alert(payload)
        print(json.dumps(norm, ensure_ascii=False, indent=2))
        raise SystemExit(0)
    if args.command == "ticket":
        with open(args.report, "r", encoding="utf-8") as f:
            report = json.load(f)
        payload = build_ticket_payload(report)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    raise SystemExit(handle_info(args))


if __name__ == "__main__":
    main()
