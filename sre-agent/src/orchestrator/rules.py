"""Rule engine for deterministic classification.

This is a minimal, config-driven rule evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


@dataclass(frozen=True)
class Rule:
    category: str
    signal: str
    op: str
    threshold: float
    confidence: float
    why: str

    def match(self, signals: Dict[str, Any]) -> bool:
        v = _to_float(signals.get(self.signal))
        if v is None:
            return False
        if self.op == ">":
            return v > self.threshold
        if self.op == ">=":
            return v >= self.threshold
        if self.op == "<":
            return v < self.threshold
        if self.op == "<=":
            return v <= self.threshold
        return False


class RuleEngine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.rules: List[Rule] = []
        for item in (config.get("rules") or []):
            try:
                self.rules.append(
                    Rule(
                        category=str(item.get("category")),
                        signal=str(item.get("signal")),
                        op=str(item.get("op")),
                        threshold=float(item.get("threshold")),
                        confidence=float(item.get("confidence", 0.5)),
                        why=str(item.get("why", "rule matched")),
                    )
                )
            except Exception:
                continue

        if not self.rules:
            self.rules = [
                Rule("IO_WAIT", "iowait_pct", ">=", 20.0, 0.8, "high iowait"),
                Rule("MEMORY", "mem_available_mb", "<=", 200.0, 0.7, "low available memory"),
                Rule("CPU", "loadavg_1m", ">=", 5.0, 0.6, "high load average"),
            ]

    def classify(self, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
        matched: List[Tuple[str, float, str, str]] = []
        for r in self.rules:
            if r.match(signals):
                matched.append((r.category, r.confidence, r.why, r.signal))

        # sort by confidence desc
        matched.sort(key=lambda x: x[1], reverse=True)
        out: List[Dict[str, Any]] = []
        for (cat, conf, why, sig) in matched[:3]:
            out.append(
                {
                    "category": cat,
                    "confidence": conf,
                    "why": f"{why} (signal={sig} value={signals.get(sig)})",
                    "evidence_refs": [],
                    "counter_evidence": self._counter_evidence(cat, signals),
                }
            )

        if not out:
            out.append(
                {
                    "category": "UNKNOWN",
                    "confidence": 0.2,
                    "why": "no rules matched",
                    "evidence_refs": [],
                    "counter_evidence": [],
                }
            )
        return out

    def _counter_evidence(self, category: str, signals: Dict[str, Any]) -> List[str]:
        ce: List[str] = []
        cat = (category or "").upper()
        if cat == "IO_WAIT":
            v = _to_float(signals.get("iowait_pct"))
            if v is not None and v < 5.0:
                ce.append(f"iowait_pct low ({v})")
        if cat == "CPU":
            v = _to_float(signals.get("loadavg_1m"))
            if v is not None and v < 1.0:
                ce.append(f"loadavg_1m low ({v})")
            iw = _to_float(signals.get("iowait_pct"))
            if iw is not None and iw >= 20.0:
                ce.append(f"iowait_pct high ({iw}) suggests IO_WAIT")
        if cat == "MEMORY":
            v = _to_float(signals.get("mem_available_mb"))
            if v is not None and v > 500.0:
                ce.append(f"mem_available_mb high ({v})")
        return ce
