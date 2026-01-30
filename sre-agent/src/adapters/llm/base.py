"""LLM adapter interface and factory."""

from typing import Any, Dict, Protocol


class LLMClient(Protocol):
    def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Return JSON that conforms to schema."""
        raise NotImplementedError

    def capabilities(self) -> Dict[str, bool]:
        """Return supported capabilities (json_schema, tool_calling, streaming)."""
        raise NotImplementedError


def create_llm_client(vendor: str, config: Dict[str, Any]) -> LLMClient:
    vendor_key = (vendor or "").lower()
    if vendor_key in ("anthropic", "claude"):
        from .anthropic import AnthropicClient
        return AnthropicClient(config)
    if vendor_key in ("openai", "gpt"):
        from .openai import OpenAIClient
        return OpenAIClient(config)
    if vendor_key in ("qwen", "dashscope"):
        from .qwen import QwenClient
        return QwenClient(config)
    raise ValueError(f"unsupported llm vendor: {vendor}")
