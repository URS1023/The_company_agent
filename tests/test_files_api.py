from __future__ import annotations

from pathlib import Path

from backend.app.core.config import settings


def test_member_can_upload_and_list_a_temporary_file(client, admin_seed, tmp_path: Path) -> None:
    original_root = settings.local_storage_root
    settings.local_storage_root = tmp_path
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin-password-123"},
        )
        assert login.status_code == 200
        uploaded = client.post(
            "/api/v1/files",
            files={
                "upload": (
                    "报价表.txt",
                    "金额,数量\n10,2\n".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["name"] == "报价表.txt"
        assert body["status"] == "ready"
        assert len(body["sha256"]) == 64
        listed = client.get("/api/v1/files")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [body["id"]]
    finally:
        settings.local_storage_root = original_root
