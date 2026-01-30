"""OpenAI LLM adapter (stub)."""

from typing import Any, Dict

from .base import LLMClient


class OpenAIClient:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def generate_json(self, prompt: str, schema: Dict[str, Any], *, temperature: float = 0.0) -> Dict[str, Any]:
        raise NotImplementedError("wire to openai sdk here")

    def capabilities(self) -> Dict[str, bool]:
        return {"json_schema": True, "tool_calling": True, "streaming": True}
