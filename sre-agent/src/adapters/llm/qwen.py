"""Qwen LLM adapter.

Implementation note:
DashScope provides an OpenAI-compatible endpoint ("compatible-mode"). This
adapter uses the `openai` python client pointed at `base_url`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional


LOG = logging.getLogger("sre_agent.llm.qwen")


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from model output."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model output")

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Common cases: fenced blocks or extra prose.
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if not m:
        m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj

    raise ValueError("could not parse JSON object from model output")


class QwenClient:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config or {}

    def _api_key(self) -> str:
        return (
            self.config.get("api_key")
            or os.getenv("SRE_LLM_API_KEY", "")
            or os.getenv("DASHSCOPE_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
        )

    def generate_json(self, prompt: str, schema: Dict[str, Any], *, temperature: float = 0.0) -> Dict[str, Any]:
        # Schema is enforced by downstream validate_schema(); here we force JSON-only output.
        from openai import OpenAI

        model = self.config.get("model") or os.getenv("SRE_LLM_MODEL") or "qwen-plus"
        base_url = self.config.get("base_url") or os.getenv("SRE_LLM_BASE_URL")
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("missing API key (set DASHSCOPE_API_KEY or SRE_LLM_API_KEY)")

        client = OpenAI(api_key=api_key, base_url=base_url)

        system = (
            "You are an SRE diagnosis assistant. "
            "Return ONLY a single JSON object that conforms to the provided schema. "
            "No markdown, no explanation, no code fences."
        )
        user = prompt

        # Use Chat Completions API for broad compatibility.
        LOG.info("qwen request model=%s base_url=%s", model, base_url or "<default>")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=float(temperature or 0.0),
        )
        content: Optional[str] = None
        try:
            content = resp.choices[0].message.content
        except Exception:
            content = None
        if not content:
            raise RuntimeError("empty completion from model")

        return _extract_json_object(content)

    def capabilities(self) -> Dict[str, bool]:
        # We can emit JSON; strict server-side json_schema support is endpoint dependent.
        return {"json_schema": False, "tool_calling": False, "streaming": False}
