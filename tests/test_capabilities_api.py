from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sqlalchemy import select

from backend.app.core.secrets import SecretManager
from backend.app.models.capabilities import (
    ConnectorVersion,
    PluginSkillBinding,
    PluginVersion,
    SecretRecord,
    SkillVersion,
    Tool,
    ToolVersion,
)


def _login(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert response.status_code == 200


def test_secret_is_encrypted_and_never_returned(client, db_session, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/secrets",
        json={
            "name": "test-provider",
            "provider": "siliconflow",
            "value": {"api_key": "secret-value"},
        },
    )
    assert response.status_code == 201
    assert "value" not in response.json()
    assert "ciphertext" not in response.json()

    async def read_secret():
        return await db_session.scalar(
            select(SecretRecord).where(SecretRecord.id == response.json()["id"])
        )

    record = asyncio.get_event_loop().run_until_complete(read_secret())
    assert record is not None
    assert "secret-value" not in record.ciphertext
    assert SecretManager().decrypt(record.nonce, record.ciphertext) == {"api_key": "secret-value"}
    rotated = client.patch(
        f"/api/v1/secrets/{response.json()['id']}",
        json={"value": {"api_key": "rotated-value"}},
    )
    assert rotated.status_code == 200
    assert "ciphertext" not in rotated.json()
    assert client.delete(f"/api/v1/secrets/{response.json()['id']}").status_code == 204


def test_skill_publish_is_versioned_and_plugin_can_clone(client, db_session, admin_seed) -> None:
    _login(client)
    skill_response = client.post(
        "/api/v1/skills",
        json={"name": "经营分析", "description": "固定分析方法", "spec": {"rules": ["不编造"]}},
    )
    assert skill_response.status_code == 201
    skill_id = skill_response.json()["id"]

    async def read_skill_version():
        return await db_session.scalar(
            select(SkillVersion).where(SkillVersion.skill_id == skill_id)
        )

    skill_version = asyncio.get_event_loop().run_until_complete(read_skill_version())
    assert client.post(f"/api/v1/skill-versions/{skill_version.id}/publish").status_code == 409
    assert client.post(f"/api/v1/skill-versions/{skill_version.id}/test-runs").status_code == 200
    published = client.post(f"/api/v1/skill-versions/{skill_version.id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    plugin_response = client.post(
        "/api/v1/plugins",
        json={
            "name": "财务经营分析",
            "description": "可复用能力",
            "spec": {"skill_version_id": skill_version.id},
        },
    )
    assert plugin_response.status_code == 201
    plugin_id = plugin_response.json()["id"]

    async def read_plugin_version():
        return await db_session.scalar(
            select(PluginVersion).where(PluginVersion.plugin_id == plugin_id)
        )

    plugin_version = asyncio.get_event_loop().run_until_complete(read_plugin_version())
    binding = client.post(
        f"/api/v1/plugin-versions/{plugin_version.id}/bindings",
        json={"skill_version_ids": [skill_version.id]},
    )
    assert binding.status_code == 204
    assert client.post(f"/api/v1/plugin-versions/{plugin_version.id}/test-runs").status_code == 200
    assert client.post(f"/api/v1/plugin-versions/{plugin_version.id}/publish").status_code == 200
    clone = client.post(f"/api/v1/plugins/{plugin_id}/clone")
    assert clone.status_code == 201
    assert clone.json()["id"] != plugin_id
    assert clone.json()["visibility"] == "private"
    cloned_version = asyncio.get_event_loop().run_until_complete(
        db_session.scalar(
            select(PluginVersion).where(PluginVersion.plugin_id == clone.json()["id"])
        )
    )
    assert cloned_version is not None
    cloned_binding = asyncio.get_event_loop().run_until_complete(
        db_session.scalar(
            select(PluginSkillBinding).where(
                PluginSkillBinding.plugin_version_id == cloned_version.id
            )
        )
    )
    assert cloned_binding is not None
    assert client.post(f"/api/v1/plugin-versions/{cloned_version.id}/test-runs").status_code == 200


def test_connector_publish_requires_admin_and_keeps_spec(client, db_session, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/connectors",
        json={
            "name": "测试 API",
            "provider": "http",
            "spec": {
                "method": "GET",
                "base_url": "http://127.0.0.1",
                "tools": [{"name": "health", "description": "Health probe"}],
            },
        },
    )
    assert response.status_code == 201
    connector_id = response.json()["id"]

    async def read_connector_version():
        return await db_session.scalar(
            select(ConnectorVersion).where(ConnectorVersion.connector_id == connector_id)
        )

    version = asyncio.get_event_loop().run_until_complete(read_connector_version())

    async def read_tool_version():
        return await db_session.scalar(
            select(ToolVersion).where(ToolVersion.connector_version_id == version.id)
        )

    tool_version = asyncio.get_event_loop().run_until_complete(read_tool_version())
    assert tool_version is not None
    assert tool_version.spec["name"] == "health"
    listed_tools = client.get(f"/api/v1/connectors/{connector_id}/tools")
    assert listed_tools.status_code == 200
    assert listed_tools.json()[0]["name"] == "health"
    assert client.post(f"/api/v1/connector-versions/{version.id}/test-runs").status_code == 200
    published = client.post(f"/api/v1/connector-versions/{version.id}/publish")
    assert published.status_code == 200
    assert published.json()["spec"]["method"] == "GET"
    published_tool = asyncio.get_event_loop().run_until_complete(read_tool_version())
    assert published_tool.status == "published"
    next_version = client.post(
        f"/api/v1/connectors/{connector_id}/versions",
        json={"spec": {"method": "GET", "tools": [{"name": "health_v2", "description": "v2"}]}},
    )
    assert next_version.status_code == 200
    assert len(client.get(f"/api/v1/connectors/{connector_id}/tools").json()) == 2


def test_data_source_rejects_inline_credentials_and_accepts_secret_reference(
    client, db_session, admin_seed
) -> None:
    _login(client)
    rejected = client.post(
        "/api/v1/data-sources",
        json={
            "name": "Finance",
            "provider": "mysql",
            "connection_config": {"host": "127.0.0.1", "password": "inline-secret"},
        },
    )
    assert rejected.status_code == 422

    secret = client.post(
        "/api/v1/secrets",
        json={"name": "finance-db", "provider": "database", "value": {"password": "test"}},
    )
    assert secret.status_code == 201
    created = client.post(
        "/api/v1/data-sources",
        json={
            "name": "Finance",
            "provider": "mysql",
            "connection_config": {"host": "127.0.0.1", "port": "3306", "database": "demo_finance"},
            "secret_id": secret.json()["id"],
        },
    )
    assert created.status_code == 201
    assert created.json()["secret_id"] == secret.json()["id"]
    assert "password" not in created.json()["connection_config"]
    source_id = created.json()["id"]
    updated = client.patch(f"/api/v1/data-sources/{source_id}", json={"name": "Finance Updated"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Finance Updated"
    connection = client.post(f"/api/v1/data-sources/{source_id}/test-connection")
    assert connection.status_code == 422
    tool_call = client.post(
        f"/api/v1/data-sources/{source_id}/tools/database.describe",
        json={"arguments": {}},
    )
    assert tool_call.status_code == 422
    assert client.delete(f"/api/v1/data-sources/{source_id}").status_code == 204
    assert source_id not in {item["id"] for item in client.get("/api/v1/data-sources").json()}
    postgres = client.post(
        "/api/v1/data-sources",
        json={
            "name": "Postgres Finance",
            "provider": "postgresql",
            "connection_config": {"host": "127.0.0.1", "port": "5432", "database": "demo"},
            "secret_id": secret.json()["id"],
        },
    )
    assert postgres.status_code == 201


def test_capability_versions_share_and_plugin_run_are_workspace_scoped(
    client, db_session, admin_seed
) -> None:
    _login(client)
    plugin_response = client.post(
        "/api/v1/plugins",
        json={"name": "版本能力", "description": "demo", "spec": {"instructions": "不编造"}},
    )
    assert plugin_response.status_code == 201
    plugin_id = plugin_response.json()["id"]
    draft_id = plugin_response.json()["draft_version_id"]
    assert client.post(f"/api/v1/plugin-versions/{draft_id}/test-runs").status_code == 200
    assert client.post(f"/api/v1/plugin-versions/{draft_id}/publish").status_code == 200
    versions = client.get(f"/api/v1/plugins/{plugin_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    shared = client.post(f"/api/v1/plugins/{plugin_id}/share", json={"visibility": "workspace"})
    assert shared.status_code == 200
    run = client.post(f"/api/v1/plugins/{plugin_id}/runs", json={"content": "运行版本能力"})
    assert run.status_code == 202
    assert run.json()["plugin_version_id"] == draft_id
    draft = client.post(
        f"/api/v1/plugins/{plugin_id}/versions", json={"spec": {"instructions": "先验证"}}
    )
    assert draft.status_code == 200
    assert draft.json()["version_number"] == 2
    updated = client.patch(
        f"/api/v1/plugins/{plugin_id}", json={"spec": {"instructions": "通过 PATCH 更新"}}
    )
    assert updated.status_code == 200


def test_connector_builder_preview_never_embeds_secret(client, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/connectors/preview",
        json={
            "name": "生成 PPT",
            "description": "根据结构化页面生成演示文稿",
            "provider": "http",
            "base_url": "https://example.test",
            "path": "/render",
            "input_schema": {"type": "object", "required": ["title"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["spec"]["name"] == "ppt"
    assert body["spec"]["secret_id"] is None
    assert any("Secret" in warning for warning in body["warnings"])


def test_http_connector_connection_and_invocation_use_tool_gateway(
    client, db_session, admin_seed
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _login(client)
        response = client.post(
            "/api/v1/connectors",
            json={
                "name": "本地健康 API",
                "provider": "http",
                "spec": {
                    "method": "GET",
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                    "path": "/health",
                    "allow_private": True,
                    "input_schema": {"type": "object"},
                    "tools": [{"name": "health", "description": "health"}],
                },
            },
        )
        assert response.status_code == 201
        connector_id = response.json()["id"]

        async def read_version():
            return await db_session.scalar(
                select(ConnectorVersion).where(ConnectorVersion.connector_id == connector_id)
            )

        version = asyncio.get_event_loop().run_until_complete(read_version())
        assert version is not None
        connection = client.post(f"/api/v1/connector-versions/{version.id}/test-connection")
        invocation = client.post(
            f"/api/v1/connector-versions/{version.id}/test-invocation",
            json={"arguments": {}},
        )
        assert connection.status_code == 200
        assert invocation.status_code == 200
        assert invocation.json()["data"] == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()


def test_capability_specs_reject_inline_credentials(client, admin_seed) -> None:
    _login(client)
    rejected = client.post(
        "/api/v1/connectors",
        json={
            "name": "泄露凭据",
            "provider": "http",
            "spec": {"headers": {"Authorization": "Bearer hard-coded"}},
        },
    )
    assert rejected.status_code == 422


def test_skill_version_routes_and_tool_toggle_are_exercisable(
    client, db_session, admin_seed
) -> None:
    _login(client)
    skill = client.post(
        "/api/v1/skills", json={"name": "可回滚 Skill", "spec": {"rules": ["先验证"]}}
    ).json()
    skill_versions = client.get(f"/api/v1/skills/{skill['id']}/versions")
    assert skill_versions.status_code == 200
    assert len(skill_versions.json()) == 1
    initial_version_id = skill_versions.json()[0]["id"]
    assert client.post(f"/api/v1/skill-versions/{initial_version_id}/test-runs").status_code == 200
    assert client.post(f"/api/v1/skill-versions/{initial_version_id}/publish").status_code == 200
    new_version = client.post(
        f"/api/v1/skills/{skill['id']}/versions",
        json={"name": "可回滚 Skill", "spec": {"rules": ["新规则"]}},
    )
    assert new_version.status_code == 200
    patched = client.patch(
        f"/api/v1/skills/{skill['id']}",
        json={"spec": {"rules": ["通过 PATCH 创建 Draft"]}},
    )
    assert patched.status_code == 200
    rollback = client.post(f"/api/v1/skills/{skill['id']}/rollback/{initial_version_id}")
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "draft"

    connector = client.post(
        "/api/v1/connectors",
        json={
            "name": "Tool Toggle",
            "provider": "http",
            "spec": {"tools": [{"name": "toggle_me", "description": "test"}]},
        },
    ).json()

    async def read_tool():
        return await db_session.scalar(select(Tool).where(Tool.connector_id == connector["id"]))

    tool = asyncio.get_event_loop().run_until_complete(read_tool())
    assert tool is not None
    toggled = client.patch(f"/api/v1/tools/{tool.id}", json={"status": "disabled"})
    assert toggled.status_code == 200
    assert toggled.json()["status"] == "disabled"


def test_mcp_connector_discovers_and_invokes_streamable_http_tools(client, admin_seed) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            method = request["method"]
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18"}
            elif method == "tools/list":
                result = {"tools": [{"name": "echo", "description": "echo"}]}
            else:
                result = {"content": [{"type": "text", "text": "ok"}]}
            body = json.dumps(
                {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _login(client)
        response = client.post(
            "/api/v1/connectors",
            json={
                "name": "本地 MCP",
                "provider": "mcp",
                "spec": {
                    "endpoint": f"http://127.0.0.1:{server.server_port}/mcp",
                    "allow_private": True,
                },
            },
        )
        assert response.status_code == 201
        connector_id = response.json()["id"]
        tools = client.get(f"/api/v1/connectors/{connector_id}/tools")
        assert tools.status_code == 200
        assert tools.json()[0]["name"] == "echo"
        versions = client.get(f"/api/v1/connectors/{connector_id}/versions")
        assert versions.status_code == 200
        version_id = versions.json()[0]["id"]
        invocation = client.post(
            f"/api/v1/connector-versions/{version_id}/test-invocation",
            json={"tool_name": "echo", "arguments": {"text": "hi"}},
        )
        assert invocation.status_code == 200
        assert invocation.json()["data"]["content"][0]["text"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
