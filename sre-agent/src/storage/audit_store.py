"""Audit store."""

import json
import os
from typing import Any, Dict


class AuditStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def write(self, record: Dict[str, Any]) -> None:
        if not self.path:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_all(self) -> list[Dict[str, Any]]:
        if not self.path or not os.path.exists(self.path):
            return []
        records: list[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        return records

    def read_session(self, session_id: str) -> list[Dict[str, Any]]:
        return [r for r in self.read_all() if (r.get("session_id") == session_id)]
