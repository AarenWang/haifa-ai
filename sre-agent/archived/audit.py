import json
from datetime import datetime, timezone
from typing import Dict, Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_audit(path: str, record: Dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
