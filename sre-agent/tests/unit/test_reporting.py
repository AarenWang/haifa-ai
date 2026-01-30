import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from reporting.prompt_templates import build_evidence_prompt, build_report_prompt
from reporting.schema_validate import validate_schema


class TestReporting(unittest.TestCase):
    def test_build_prompts(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        p1 = build_evidence_prompt("host", "svc", 30, schema)
        p2 = build_report_prompt({"a": "b"}, schema)
        self.assertIn("Schema", p1)
        self.assertIn("Schema", p2)

    def test_validate_schema_ok(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        validate_schema({"a": "b"}, schema)

    def test_validate_schema_fail(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        with self.assertRaises(ValueError):
            validate_schema({"a": 1}, schema)


if __name__ == "__main__":
    unittest.main()
