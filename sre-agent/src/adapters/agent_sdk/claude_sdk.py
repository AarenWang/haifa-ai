"""Claude Agent SDK adapter (stub)."""

from typing import Any, Dict

from .base import AgentSDKClient


class ClaudeSDKClientAdapter:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def run(self, prompt: str, tools: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("wire to claude agent sdk here")

    def capabilities(self) -> Dict[str, bool]:
        return {"mcp": True, "tool_calling": True, "streaming": True}
