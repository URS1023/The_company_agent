import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from backend.app.models.capabilities import ModelProbeResult


def test_liveness_is_local_and_does_not_require_dependencies() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_summary_does_not_expose_provider_secrets() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/system/config")
    assert response.status_code == 200
    body = response.json()
    assert body["chat_provider"] == "agnes"
    assert body["embedding_model"] == "BAAI/bge-m3"
    assert "api_key" not in body
    assert "secret" not in body


def test_model_profiles_are_not_exposed_to_unauthenticated_users() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/admin/model-profiles")
    assert response.status_code == 401


def test_state_changing_cross_origin_request_is_rejected() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://attacker.example"},
        json={"username": "admin", "password": "irrelevant"},
    )
    assert response.status_code == 403


def test_ready_endpoint_reports_dependency_status_without_crashing(client, monkeypatch) -> None:
    async def ok_ping():
        return True, "ok"

    import backend.app.api.v1.endpoints.health as health_endpoint

    monkeypatch.setattr(health_endpoint, "database_ping", ok_ping)
    monkeypatch.setattr(health_endpoint, "redis_ping", ok_ping)
    monkeypatch.setattr(health_endpoint, "elasticsearch_ping", ok_ping)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_admin_model_probe_unknown_profile_is_rejected(client, admin_seed) -> None:
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
        ).status_code
        == 200
    )
    response = client.post("/api/v1/admin/model-profiles/unknown/probe")
    assert response.status_code == 404


def test_admin_model_probe_records_success_without_exposing_key(
    client, admin_seed, db_session, monkeypatch
) -> None:
    class FakeResponse:
        text = "OK"

    class FakeClient:
        async def chat(self, **kwargs):
            return FakeResponse()

    import backend.app.api.v1.endpoints.admin as admin_endpoint

    monkeypatch.setattr(admin_endpoint, "agnes_client", lambda: FakeClient())
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
        ).status_code
        == 200
    )
    response = client.post("/api/v1/admin/model-profiles/reasoning/probe")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "api_key" not in response.text

    async def read_probe():
        return await db_session.scalar(
            select(ModelProbeResult).where(ModelProbeResult.status == "ready")
        )

    assert asyncio.get_event_loop().run_until_complete(read_probe()) is not None
