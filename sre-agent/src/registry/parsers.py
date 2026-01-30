"""Parsers registry.

Parsers are intentionally lightweight and deterministic.
They should never fail hard; return best-effort structured fields.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _first_line(text: str) -> str:
    lines = (text or "").splitlines()
    return lines[0] if lines else ""


def parse_output(cmd_id: str, output: str) -> Dict[str, Any]:
    out = output or ""
    parsed: Dict[str, Any] = {"cmd_id": cmd_id}

    if cmd_id == "uptime":
        line = _first_line(out)
        parsed["uptime_line"] = line
        m = re.search(r"load average[s]?:\s*([0-9.]+)[, ]+([0-9.]+)[, ]+([0-9.]+)", line)
        if m:
            parsed["loadavg"] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
        return parsed

    if cmd_id == "loadavg":
        parts = _first_line(out).split()
        if len(parts) >= 3:
            try:
                parsed["loadavg"] = [float(parts[0]), float(parts[1]), float(parts[2])]
            except Exception:
                pass
        return parsed

    if cmd_id in ("free",):
        # free -m output
        mem_line = ""
        swap_line = ""
        for line in out.splitlines():
            if line.lower().startswith("mem:"):
                mem_line = line
            if line.lower().startswith("swap:"):
                swap_line = line
        if mem_line:
            cols = mem_line.split()
            # Mem: total used free shared buff/cache available
            if len(cols) >= 7:
                parsed["mem_mb"] = {
                    "total": _to_int(cols[1]),
                    "used": _to_int(cols[2]),
                    "free": _to_int(cols[3]),
                    "available": _to_int(cols[6]),
                }
        if swap_line:
            cols = swap_line.split()
            if len(cols) >= 4:
                parsed["swap_mb"] = {"total": _to_int(cols[1]), "used": _to_int(cols[2]), "free": _to_int(cols[3])}
        return parsed

    if cmd_id == "iostat":
        # best-effort: capture %iowait line if present
        for line in out.splitlines():
            if "%iowait" in line and "%idle" in line:
                parsed["cpu_iostat_header"] = line.strip()
            if line.strip().startswith("avg-cpu"):
                parsed["avg_cpu_section"] = True
        # common format has a line with numbers after avg-cpu header
        # try to parse iowait if header is present in previous line
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "%iowait" in line and i + 1 < len(lines):
                header = line.split()
                vals = lines[i + 1].split()
                if len(vals) == len(header):
                    parsed["iostat_avg_cpu"] = {h: _to_float(v) for h, v in zip(header, vals)}
                break
        return parsed

    if cmd_id in ("mpstat", "vmstat", "top", "ps_cpu", "ps_mem", "df", "jps", "jstat", "jstack", "journalctl"):
        parsed["first_line"] = _first_line(out)[:500]
        return parsed

    parsed["raw"] = out
    return parsed


def _to_int(v: str) -> Optional[int]:
    try:
        return int(float(v))
    except Exception:
        return None


def _to_float(v: str) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None
