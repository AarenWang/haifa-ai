"""Local execution adapter."""

import subprocess
from typing import Dict


class LocalExecutor:
    def __init__(self, config: Dict[str, str]) -> None:
        self.config = config

    def run(self, host: str, command: str, timeout: int = 30) -> str:
        _ = host
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout or ""
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr
            return output
        except subprocess.TimeoutExpired:
            return f"command timeout after {timeout}s"
        except Exception as exc:
            return f"exec error: {type(exc).__name__}: {exc}"
