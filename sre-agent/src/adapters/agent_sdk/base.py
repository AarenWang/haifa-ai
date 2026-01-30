"""Agent SDK adapter interface and factory."""

from typing import Any, Dict, Protocol


class AgentSDKClient(Protocol):
    def run(self, prompt: str, tools: Dict[str, Any]) -> Dict[str, Any]:
        """Run a tool-aware agent session and return structured output."""
        raise NotImplementedError

    def capabilities(self) -> Dict[str, bool]:
        """Return supported capabilities (mcp, tool_calling, streaming)."""
        raise NotImplementedError


def create_agent_sdk_client(vendor: str, config: Dict[str, Any]) -> AgentSDKClient:
    vendor_key = (vendor or "").lower()
    if vendor_key in ("claude_sdk", "anthropic_sdk"):
        from .claude_sdk import ClaudeSDKClientAdapter
        return ClaudeSDKClientAdapter(config)
    if vendor_key in ("langgraph",):
        from .langgraph import LangGraphAdapter
        return LangGraphAdapter(config)
    raise ValueError(f"unsupported agent sdk: {vendor}")
