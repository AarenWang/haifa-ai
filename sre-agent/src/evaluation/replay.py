"""Offline replay for evidence packs.

The replay uses the stored evidence_pack JSON and runs deterministic rule engine
to verify classification + schema validity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from jsonschema import validate

from orchestrator.rules import RuleEngine


@dataclass(frozen=True)
class ReplayResult:
    ok: bool
    predicted: str
    expected: str
    schema_ok: bool


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def replay_one(evidence_pack_path: str, schema_path: str, expected_category: str) -> ReplayResult:
    evidence = load_json(evidence_pack_path)
    schema = load_json(schema_path)

    schema_ok = True
    try:
        validate(instance=evidence, schema=schema)
    except Exception:
        schema_ok = False

    signals = evidence.get("signals") or {}
    engine = RuleEngine({})
    hyps = engine.classify(signals)
    predicted = hyps[0]["category"] if hyps else "UNKNOWN"

    return ReplayResult(ok=(predicted == expected_category and schema_ok), predicted=predicted, expected=expected_category, schema_ok=schema_ok)


def replay_suite(cases: List[Tuple[str, str, str]]) -> List[ReplayResult]:
    results: List[ReplayResult] = []
    for evidence_pack_path, schema_path, expected in cases:
        results.append(replay_one(evidence_pack_path, schema_path, expected))
    return results
