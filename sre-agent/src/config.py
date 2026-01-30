"""Configuration loader and merger."""

import os
from typing import Any, Dict, Iterable


def deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml_file(path: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyYAML is required to load .yaml config files") from exc

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"invalid yaml mapping: {path}")
    return data


def load_configs(paths: Iterable[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for path in paths:
        if not path:
            continue
        data = load_yaml_file(path)
        merged = deep_merge(merged, data)
    return merged


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply multi-environment overrides.

    If config has:
      environments:
        prod: { ... }
        staging: { ... }
    then SRE_ENV selects and deep-merges into base config.
    """
    env = (os.getenv("SRE_ENV") or "").strip()
    envs = config.get("environments") if isinstance(config, dict) else None
    if not env or not isinstance(envs, dict) or env not in envs:
        return config
    return deep_merge(config, envs.get(env) or {})
