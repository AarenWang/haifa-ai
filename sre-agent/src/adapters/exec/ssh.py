"""SSH execution adapter."""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any, Dict, List, Mapping


def _bash_single_quote(value: str) -> str:
    """Safely single-quote a string for bash script contexts."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


class SSHExecutor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.user = config.get("user") or os.getenv("SRE_SSH_USER", "root")
        self.password = config.get("password") or os.getenv("SRE_SSH_PASSWORD", "")
        self.port = int(config.get("port") or os.getenv("SRE_SSH_PORT", "22"))
        self.strict_host_key = (config.get("strict_host_key", "false").lower() == "true")
        self.connect_timeout = int(config.get("connect_timeout") or "10")

        # Optional remote shell init to ensure tools (e.g. jps/jstack) are on PATH.
        # Many hosts put JAVA_HOME / PATH updates in ~/.bashrc only.
        self.shell_init: List[str] = []
        init_cfg = config.get("shell_init")
        if isinstance(init_cfg, str) and init_cfg.strip():
            self.shell_init = [init_cfg.strip()]
        elif isinstance(init_cfg, list):
            self.shell_init = [str(x) for x in init_cfg if str(x).strip()]

        if config.get("source_bashrc", True):
            # Best-effort; suppress output to keep command stdout clean.
            self.shell_init.extend(
                [
                    ". /etc/profile >/dev/null 2>&1 || true",
                    ". ~/.bash_profile >/dev/null 2>&1 || true",
                    ". ~/.profile >/dev/null 2>&1 || true",
                    ". ~/.bashrc >/dev/null 2>&1 || true",
                ]
            )

        env_cfg = config.get("env")
        self.remote_env: Dict[str, str] = {}
        if isinstance(env_cfg, Mapping):
            for k, v in env_cfg.items():
                if v is None:
                    continue
                self.remote_env[str(k)] = str(v)

        path_extra = config.get("path_extra")
        self.path_extra: List[str] = []
        if isinstance(path_extra, str) and path_extra.strip():
            self.path_extra = [path_extra.strip()]
        elif isinstance(path_extra, list):
            self.path_extra = [str(x) for x in path_extra if str(x).strip()]


    def _build_remote_script(self, command: str) -> str:
        lines: List[str] = []
        for k, v in (self.remote_env or {}).items():
            if not k:
                continue
            lines.append(f"export {k}={_bash_single_quote(v)}")
        for p in self.path_extra:
            lines.append(f"export PATH={_bash_single_quote(p)}:$PATH")
        lines.extend(self.shell_init)
        lines.append(command)
        return "; ".join([x for x in lines if x.strip()])

    def run(self, host: str, command: str, timeout: int = 30) -> str:
        if self.password:
            return self._run_paramiko(host, command, timeout)
        return self._run_subprocess(host, command, timeout)

    def _run_subprocess(self, host: str, command: str, timeout: int) -> str:
        target = host if "@" in host else f"{self.user}@{host}"

        script = self._build_remote_script(command)
        wrapped = f"bash -lc {shlex.quote(script)}"

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

            script = self._build_remote_script(command)
            wrapped = f"bash -lc {shlex.quote(script)}"
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
