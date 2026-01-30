"""Input validators."""

import re

SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def validate_pid(pid: str) -> bool:
    return bool(pid) and pid.isdigit()


def validate_service(service: str) -> bool:
    return bool(service) and bool(SERVICE_RE.match(service))
