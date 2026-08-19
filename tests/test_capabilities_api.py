from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.core.secrets import SecretManager
from backend.app.models.capabilities import (
    ConnectorVersion,
    PluginVersion,
    SecretRecord,
    SkillVersion,
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


def test_connector_publish_requires_admin_and_keeps_spec(client, db_session, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/connectors",
        json={
            "name": "测试 API",
            "provider": "http",
            "spec": {"method": "GET", "base_url": "http://127.0.0.1"},
        },
    )
    assert response.status_code == 201
    connector_id = response.json()["id"]

    async def read_connector_version():
        return await db_session.scalar(
            select(ConnectorVersion).where(ConnectorVersion.connector_id == connector_id)
        )

    version = asyncio.get_event_loop().run_until_complete(read_connector_version())
    assert client.post(f"/api/v1/connector-versions/{version.id}/test-runs").status_code == 200
    published = client.post(f"/api/v1/connector-versions/{version.id}/publish")
    assert published.status_code == 200
    assert published.json()["spec"]["method"] == "GET"


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
