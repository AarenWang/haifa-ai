"""Minimal end-to-end test for local exec mode."""

import os
import subprocess
import sys


def main() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(root, "src")

    cmd = [
        sys.executable,
        "-m",
        "src.cli.sre_agent_cli",
        "exec",
        "--host",
        "localhost",
        "--cmd-id",
        "uptime",
        "--exec-mode",
        "local",
        "--audit-log",
        os.path.join(root, "report", "e2e_audit.log"),
    ]

    result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print("failed", result.stdout, result.stderr)
        return result.returncode

    if not result.stdout.strip():
        print("empty output")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
