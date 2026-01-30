"""Report builder using LLM adapter and schema-aligned prompt."""

from typing import Any, Dict

from adapters.llm.base import LLMClient
from reporting.prompt_templates import build_report_prompt
from reporting.schema_validate import validate_schema
from policy.action_filter import filter_actions


def build_report(llm: LLMClient, evidence: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    prompt = build_report_prompt(evidence, schema)
    report = llm.generate_json(prompt, schema, temperature=0.2)
    # Enforce READ_ONLY/LOW action policy even if schema passes.
    policy = evidence.get("policy", {}) if isinstance(evidence, dict) else {}
    allowed_risks = policy.get("allowed_risks", ["READ_ONLY", "LOW"])
    deny_keywords = policy.get("deny_keywords", [])
    if isinstance(report, dict) and isinstance(report.get("next_actions"), list):
        allowed, blocked = filter_actions(report.get("next_actions") or [], allowed_risks, deny_keywords)
        report["next_actions"] = allowed
        report.setdefault("audit", {})
        if isinstance(report.get("audit"), dict):
            report["audit"].setdefault("blocked_actions", blocked)
    if isinstance(report, dict) and isinstance(report.get("audit"), dict):
        report["audit"].setdefault("blocked_actions", [])
    validate_schema(report, schema)
    return report
