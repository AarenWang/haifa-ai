"""Command registry helpers."""

from typing import Any, Dict, Optional


def load_commands(config: Dict[str, Any]) -> Dict[str, Any]:
    return config.get("commands", {})


def get_command_meta(commands: Dict[str, Any], cmd_id: str) -> Dict[str, Any]:
    if cmd_id not in commands:
        raise KeyError(f"unknown cmd_id: {cmd_id}")
    meta = commands[cmd_id]
    if not isinstance(meta, dict) or "cmd" not in meta:
        raise ValueError(f"invalid command meta for: {cmd_id}")
    return meta


def render_command(template: str, service: Optional[str] = None, pid: Optional[str] = None) -> str:
    if "{service}" in template and not service:
        raise ValueError("service is required for this command")
    if "{pid}" in template and not pid:
        raise ValueError("pid is required for this command")
    return template.format(service=service or "", pid=pid or "")
