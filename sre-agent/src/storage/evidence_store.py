"""Evidence store.

Stores three layers:
- raw: original command output
- redacted: output after redaction
- parsed: structured extraction

Refs are returned as workspace-relative paths under the session directory.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EvidenceRefs:
    raw_ref: str
    redacted_ref: str
    parsed_ref: Optional[str] = None


class EvidenceStore:
    def __init__(self, base_dir: str, session_id: str) -> None:
        self.base_dir = base_dir
        self.session_id = session_id
        self.session_dir = os.path.join(base_dir, session_id)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for sub in ("raw", "redacted", "parsed", "index"):
            os.makedirs(os.path.join(self.session_dir, sub), exist_ok=True)

    def _new_id(self) -> str:
        return uuid.uuid4().hex

    def put_raw(self, cmd_id: str, data: str) -> str:
        evid = self._new_id()
        path = os.path.join(self.session_dir, "raw", f"{cmd_id}-{evid}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data or "")
        return os.path.relpath(path, self.base_dir)

    def put_redacted(self, cmd_id: str, data: str) -> str:
        evid = self._new_id()
        path = os.path.join(self.session_dir, "redacted", f"{cmd_id}-{evid}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data or "")
        return os.path.relpath(path, self.base_dir)

    def put_parsed(self, cmd_id: str, data: Dict[str, Any]) -> str:
        evid = self._new_id()
        path = os.path.join(self.session_dir, "parsed", f"{cmd_id}-{evid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=True, indent=2)
        return os.path.relpath(path, self.base_dir)

    def write_index(self, name: str, payload: Dict[str, Any]) -> str:
        path = os.path.join(self.session_dir, "index", f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload or {}, f, ensure_ascii=True, indent=2)
        return os.path.relpath(path, self.base_dir)
