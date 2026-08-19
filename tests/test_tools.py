from __future__ import annotations

import json

import httpx
import pytest

from backend.app.services.parameter_compiler import compile_arguments
from backend.app.tools.database import ReadOnlySqlError, validate_read_only_sql
from backend.app.tools.gateway import (
    ToolValidationError,
    validate_arguments,
    validate_source_policy,
)
from backend.app.tools.http import HttpConnectorError, HttpResult, invoke, validate_target
from backend.app.tools.mcp import StreamableHttpMcpClient
from backend.app.tools.sandbox import SandboxError, run_safe_python, run_trusted_sandbox


def test_read_only_sql_accepts_select_and_rejects_side_effects() -> None:
    assert "SELECT" in validate_read_only_sql("SELECT updated_at FROM projects")
    assert "SELECT" in validate_read_only_sql(
        "WITH recent AS (SELECT 1 AS id) SELECT * FROM recent"
    )
    for sql in [
        "UPDATE projects SET name = 'x'",
        "SELECT 1; DELETE FROM projects",
        "SELECT SLEEP(1)",
        "SELECT * FROM projects FOR UPDATE",
    ]:
        with pytest.raises(ReadOnlySqlError):
            validate_read_only_sql(sql)


def test_http_target_blocks_private_and_userinfo() -> None:
    with pytest.raises(HttpConnectorError):
        validate_target("http://127.0.0.1:8000")
    with pytest.raises(HttpConnectorError):
        validate_target("https://user:password@example.com/api")
    assert validate_target("http://127.0.0.1:8000", allow_private=True).startswith("http://")


@pytest.mark.asyncio
async def test_http_connector_normalizes_json_and_limits_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "ok"})

    result = await invoke(
        base_url="http://127.0.0.1:8000",
        path="/health",
        allow_private=True,
        transport=httpx.MockTransport(handler),
    )
    assert result.status_code == 200
    assert result.data == {"status": "ok"}


def test_gateway_validates_json_schema() -> None:
    validate_arguments(
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        {"name": "demo"},
    )
    with pytest.raises(ToolValidationError):
        validate_arguments(
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            {},
        )


def test_result_normalizer_exposes_artifact_references() -> None:
    from backend.app.tools.gateway import normalize_result

    normalized = normalize_result(
        HttpResult(200, {}, {"url": "https://example.test/report.pptx", "type": "presentation"})
    )
    assert normalized["status"] == "success"
    assert normalized["artifacts"][0]["type"] == "presentation"


@pytest.mark.asyncio
async def test_mcp_streamable_http_json_rpc_round_trip() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json", "Mcp-Session-Id": "session-1"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"protocolVersion": "2025-06-18"},
                },
            )
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "echo"}]}},
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"text": "ok"}]}},
        )

    client = StreamableHttpMcpClient("http://mcp.test/mcp", transport=httpx.MockTransport(handler))
    initialized = await client.initialize()
    assert initialized["protocolVersion"] == "2025-06-18"
    assert client.session_id == "session-1"
    assert (await client.list_tools())[0]["name"] == "echo"
    assert (await client.call_tool("echo", {"text": "ok"}))["content"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_native_sandbox_allows_trusted_analyzer_but_rejects_arbitrary_code() -> None:
    result = await run_trusted_sandbox(
        "finance.analyze", {"rows": [{"revenue": 10, "cost": 4}], "budget": 5}
    )
    assert result["summary"]["profit"] == 6.0
    with pytest.raises(SandboxError, match="ARBITRARY_PYTHON_DISABLED"):
        await run_trusted_sandbox("python.execute", {"code": "print(1)"})
    safe = await run_safe_python(
        "result = [row['revenue'] - row['cost'] for row in data]",
        data=[{"revenue": 10, "cost": 4}],
    )
    assert safe["data"] == [6]
    with pytest.raises(SandboxError, match="PYTHON_NODE_NOT_ALLOWED"):
        await run_safe_python("import os\nresult = 1")


def test_parameter_compiler_fills_defaults_and_source_policy_blocks_llm_value() -> None:
    compiled = compile_arguments(
        {"project_id": "P-1"},
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["project_id"],
        },
    )
    assert compiled["limit"] == 100
    with pytest.raises(ToolValidationError):
        validate_source_policy(
            {"amount": 100, "__sources": {"amount": "llm"}},
            {"amount": {"source": "database", "allow_llm_generate": False}},
        )
