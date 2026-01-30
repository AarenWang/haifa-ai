"""Schema validation."""

from typing import Any, Dict

from jsonschema import validate
from jsonschema.exceptions import ValidationError


def validate_schema(payload: Dict[str, Any], schema: Dict[str, Any]) -> None:
    try:
        validate(instance=payload, schema=schema)
    except ValidationError as exc:
        path = ".".join([str(p) for p in exc.path]) if exc.path else "<root>"
        raise ValueError(f"schema validation failed at {path}: {exc.message}") from exc
