"""MCP execution adapter (stub)."""

from typing import Dict, Any


class MCPExecutor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("wire to mcp tool calling here")
