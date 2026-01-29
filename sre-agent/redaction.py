import re
from hashlib import sha256
from typing import Tuple, List

RULES = [
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SECRET", re.compile(r"(AKIA|ASIA|sk-|token=|apikey=)[A-Za-z0-9\-_]+", re.IGNORECASE)),
    ("PATH", re.compile(r"/(?:[\w.-]+/)+[\w.-]+")),
    ("USER", re.compile(r"\buser(?:name)?=\w+\b", re.IGNORECASE)),
]


def redact(text: str) -> Tuple[str, List[str], int]:
    replaced_count = 0
    applied = []
    redacted = text
    for name, pattern in RULES:
        matches = pattern.findall(redacted)
        if matches:
            applied.append(name)
            replaced_count += len(matches)
            redacted = pattern.sub(f"<{name}>", redacted)
    return redacted, applied, replaced_count


def hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
