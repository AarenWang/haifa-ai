#!/usr/bin/env python3

import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay and evaluate evidence packs")
    ap.add_argument("--cases", default=os.path.join("tests", "fixtures", "cases.json"))
    ap.add_argument("--schema", default=os.path.join("schemas", "evidence_schema.json"))
    args = ap.parse_args()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, os.path.join(root, "src"))

    from evaluation.replay import replay_one
    from evaluation.metrics import compute_metrics

    with open(os.path.join(root, args.cases), "r", encoding="utf-8") as f:
        cases = json.load(f)

    tmp_dir = os.path.join(root, "report", "replay_suite")
    os.makedirs(tmp_dir, exist_ok=True)

    results = []
    for c in cases:
        p = os.path.join(tmp_dir, f"{c['id']}.json")
        evidence = {
            "meta": {"host": "h", "service": "svc", "timestamp": "2026-01-01T00:00:00Z"},
            "snapshots": [],
            "hypothesis": [],
            "next_checks": [],
            "signals": c["signals"],
            "policy": {"allowed_risks": ["READ_ONLY"], "deny_keywords": []},
        }
        with open(p, "w", encoding="utf-8") as wf:
            json.dump(evidence, wf, ensure_ascii=True, indent=2)

        res = replay_one(p, os.path.join(root, args.schema), c["expected_category"])
        results.append(res)

    m = compute_metrics(results)
    print(json.dumps({"total": m.total, "accuracy": m.accuracy, "schema_pass_rate": m.schema_pass_rate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
