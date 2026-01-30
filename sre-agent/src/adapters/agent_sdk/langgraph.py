"""LangGraph adapter (stub)."""

from typing import Any, Dict

from .base import AgentSDKClient


class LangGraphAdapter:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def run(self, prompt: str, tools: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("wire to langgraph here")

    def capabilities(self) -> Dict[str, bool]:
        return {"mcp": False, "tool_calling": True, "streaming": False}
