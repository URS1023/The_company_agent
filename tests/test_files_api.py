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


def test_file_upload_supports_batch_and_rejects_unknown_formats(
    client, admin_seed, tmp_path: Path
) -> None:
    original_root = settings.local_storage_root
    settings.local_storage_root = tmp_path
    try:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
            ).status_code
            == 200
        )
        batch = client.post(
            "/api/v1/files/batch",
            files=[
                ("uploads", ("one.txt", b"one", "text/plain")),
                ("uploads", ("two.csv", b"a,b\n1,2\n", "text/csv")),
            ],
        )
        assert batch.status_code == 201
        assert {item["name"] for item in batch.json()} == {"one.txt", "two.csv"}
        rejected = client.post(
            "/api/v1/files", files={"upload": ("malware.exe", b"x", "application/octet-stream")}
        )
        assert rejected.status_code == 415
        bad_magic = client.post(
            "/api/v1/files", files={"upload": ("not-a-pdf.pdf", b"plain text", "application/pdf")}
        )
        assert bad_magic.status_code == 415
    finally:
        settings.local_storage_root = original_root
