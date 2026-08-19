from fastapi.testclient import TestClient

from backend.app.main import app


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
