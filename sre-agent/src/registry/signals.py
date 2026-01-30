"""Signals registry.

Turn parsed outputs into normalized signals.
"""

from __future__ import annotations

from typing import Any, Dict


def extract_signals(parsed: Dict[str, Any]) -> Dict[str, Any]:
    cmd_id = parsed.get("cmd_id")
    signals: Dict[str, Any] = {}

    if cmd_id in ("uptime", "loadavg"):
        if "loadavg" in parsed:
            signals["loadavg_1m"] = parsed["loadavg"][0]
            signals["loadavg_5m"] = parsed["loadavg"][1]
            signals["loadavg_15m"] = parsed["loadavg"][2]

    if cmd_id == "free":
        mem = parsed.get("mem_mb") or {}
        swap = parsed.get("swap_mb") or {}
        if mem.get("available") is not None:
            signals["mem_available_mb"] = mem.get("available")
        if mem.get("used") is not None:
            signals["mem_used_mb"] = mem.get("used")
        if swap.get("used") is not None:
            signals["swap_used_mb"] = swap.get("used")

    if cmd_id == "iostat":
        cpu = parsed.get("iostat_avg_cpu") or {}
        # key varies across versions; try common ones
        for k in ("%iowait", "iowait"):
            if cpu.get(k) is not None:
                signals["iowait_pct"] = cpu.get(k)
                break

    return {"signals": signals}
