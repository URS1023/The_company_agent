from __future__ import annotations

import json
from typing import Any

import httpx


class McpError(RuntimeError):
    pass


class StreamableHttpMcpClient:
    """Minimal MCP JSON-RPC client for Streamable HTTP; stdio is a separate secure runner."""

    def __init__(
        self,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.headers = headers or {}
        self.transport = transport
        self._next_id = 0
        self.session_id: str | None = None

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            body["params"] = params
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
            response = await client.post(self.endpoint, headers=headers, json=body)
        if response.is_error:
            raise McpError(f"MCP server returned HTTP {response.status_code}")
        if response.headers.get("mcp-session-id"):
            self.session_id = response.headers["mcp-session-id"]
        if "text/event-stream" in response.headers.get("content-type", ""):
            data_lines = [
                line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")
            ]
            if not data_lines:
                raise McpError("MCP stream contained no JSON response")
            return json.loads(data_lines[-1])
        return response.json()

    async def initialize(
        self, client_name: str = "company-agent", version: str = "0.1.0"
    ) -> dict[str, Any]:
        response = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": version},
            },
        )
        if response.get("error"):
            raise McpError(str(response["error"]))
        return response.get("result", {})

    async def list_tools(self) -> list[dict[str, Any]]:
        response = await self._request("tools/list")
        if response.get("error"):
            raise McpError(str(response["error"]))
        return response.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("tools/call", {"name": name, "arguments": arguments})
        if response.get("error"):
            raise McpError(str(response["error"]))
        return response.get("result", {})


__all__ = ["McpError", "StreamableHttpMcpClient"]
