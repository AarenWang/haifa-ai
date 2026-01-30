"""SSH execution adapter."""

import os
import shlex
import subprocess
from typing import Dict


class SSHExecutor:
    def __init__(self, config: Dict[str, str]) -> None:
        self.user = config.get("user") or os.getenv("SRE_SSH_USER", "root")
        self.password = config.get("password") or os.getenv("SRE_SSH_PASSWORD", "")
        self.port = int(config.get("port") or os.getenv("SRE_SSH_PORT", "22"))
        self.strict_host_key = (config.get("strict_host_key", "false").lower() == "true")
        self.connect_timeout = int(config.get("connect_timeout") or "10")

    def run(self, host: str, command: str, timeout: int = 30) -> str:
        if self.password:
            return self._run_paramiko(host, command, timeout)
        return self._run_subprocess(host, command, timeout)

    def _run_subprocess(self, host: str, command: str, timeout: int) -> str:
        target = host if "@" in host else f"{self.user}@{host}"
        wrapped = f"bash -l -c {shlex.quote(command)}"

        strict = "yes" if self.strict_host_key else "no"
        cmd = (
            "ssh -o BatchMode=yes "
            f"-o StrictHostKeyChecking={strict} "
            f"-o ConnectTimeout={self.connect_timeout} "
            f"-p {self.port} "
            f"{shlex.quote(target)} {shlex.quote(wrapped)}"
        )

        try:
            result = subprocess.run(
                cmd,
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
            return f"ssh error: {type(exc).__name__}: {exc}"

    def _run_paramiko(self, host: str, command: str, timeout: int) -> str:
        try:
            import paramiko
        except Exception as exc:
            return f"paramiko not available: {exc}"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                port=self.port,
                username=self.user,
                password=self.password,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            wrapped = f"bash -l -c {command!r}"
            stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
            _ = stdin
            out = stdout.read().decode("utf-8", errors="replace") if stdout else ""
            err = stderr.read().decode("utf-8", errors="replace") if stderr else ""
            return out + ("\n[stderr]\n" + err if err else "")
        except Exception as exc:
            return f"ssh error: {type(exc).__name__}: {exc}"
        finally:
            try:
                client.close()
            except Exception:
                pass
