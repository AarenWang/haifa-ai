import json
import os
import sys
import unittest
from datetime import datetime, timezone


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from evaluation.replay import replay_one  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestReplay(unittest.TestCase):
    def test_replay_fixture_cases(self) -> None:
        fixtures = os.path.join(ROOT_DIR, "tests", "fixtures", "cases.json")
        with open(fixtures, "r", encoding="utf-8") as f:
            cases = json.load(f)

        schema_path = os.path.join(ROOT_DIR, "schemas", "evidence_schema.json")
        tmp_dir = os.path.join(ROOT_DIR, "report", "replay_tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        for c in cases:
            evidence = {
                "meta": {"host": "h", "service": "svc", "timestamp": now_iso()},
                "snapshots": [],
                "hypothesis": [],
                "next_checks": [],
                "signals": c["signals"],
                "policy": {"allowed_risks": ["READ_ONLY"], "deny_keywords": []},
            }
            p = os.path.join(tmp_dir, f"{c['id']}.json")
            with open(p, "w", encoding="utf-8") as wf:
                json.dump(evidence, wf, ensure_ascii=True, indent=2)

            res = replay_one(p, schema_path, c["expected_category"])
            self.assertTrue(res.schema_ok)
            self.assertEqual(res.predicted, c["expected_category"])


if __name__ == "__main__":
    unittest.main()
