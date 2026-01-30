"""Simple evaluation metrics for replay results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from evaluation.replay import ReplayResult


@dataclass(frozen=True)
class Metrics:
    total: int
    correct: int
    schema_ok: int

    @property
    def accuracy(self) -> float:
        return (self.correct / self.total) if self.total else 0.0

    @property
    def schema_pass_rate(self) -> float:
        return (self.schema_ok / self.total) if self.total else 0.0


def compute_metrics(results: List[ReplayResult]) -> Metrics:
    total = len(results)
    correct = sum(1 for r in results if r.predicted == r.expected)
    schema_ok = sum(1 for r in results if r.schema_ok)
    return Metrics(total=total, correct=correct, schema_ok=schema_ok)
