import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from registry.commands import get_command_meta, load_commands, render_command


class TestRegistry(unittest.TestCase):
    def test_load_commands(self) -> None:
        cfg = {"commands": {"uptime": {"cmd": "uptime", "risk": "READ_ONLY"}}}
        commands = load_commands(cfg)
        self.assertIn("uptime", commands)

    def test_get_command_meta(self) -> None:
        commands = {"uptime": {"cmd": "uptime", "risk": "READ_ONLY"}}
        meta = get_command_meta(commands, "uptime")
        self.assertEqual(meta["cmd"], "uptime")

    def test_get_command_meta_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_command_meta({}, "missing")

    def test_render_command_requires_service(self) -> None:
        with self.assertRaises(ValueError):
            render_command("journalctl -u {service}")

    def test_render_command_requires_pid(self) -> None:
        with self.assertRaises(ValueError):
            render_command("cat /proc/{pid}/status")

    def test_render_command_substitutes(self) -> None:
        cmd = render_command("cat /proc/{pid}/status", pid="123")
        self.assertIn("/proc/123/status", cmd)


if __name__ == "__main__":
    unittest.main()
