import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from policy.command_policy import is_command_allowed
from policy.validators import validate_pid, validate_service


class TestPolicy(unittest.TestCase):
    def test_command_allowed_when_risk_ok(self) -> None:
        meta = {"cmd": "uptime", "risk": "READ_ONLY"}
        self.assertTrue(is_command_allowed(meta, ["READ_ONLY"], []))

    def test_command_blocked_by_risk(self) -> None:
        meta = {"cmd": "uptime", "risk": "LOW"}
        self.assertFalse(is_command_allowed(meta, ["READ_ONLY"], []))

    def test_command_blocked_by_keyword(self) -> None:
        meta = {"cmd": "kill -9 123", "risk": "READ_ONLY"}
        self.assertFalse(is_command_allowed(meta, ["READ_ONLY"], ["kill"]))

    def test_validate_pid(self) -> None:
        self.assertTrue(validate_pid("123"))
        self.assertFalse(validate_pid("abc"))

    def test_validate_service(self) -> None:
        self.assertTrue(validate_service("svc-1"))
        self.assertFalse(validate_service("bad name"))


if __name__ == "__main__":
    unittest.main()
