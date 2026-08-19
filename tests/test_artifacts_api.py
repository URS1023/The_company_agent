from __future__ import annotations

import asyncio

from backend.app.core.config import settings
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.core.storage import LocalFileStorage
from backend.app.models.capabilities import Artifact
from backend.app.models.runtime import Run


def test_artifact_preview_and_download_require_workspace_ownership(
    client, db_session, admin_seed, tmp_path
):
    original_root = settings.local_storage_root
    settings.local_storage_root = tmp_path
    try:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin-password-123"},
            ).status_code
            == 200
        )
        conversation = client.post("/api/v1/conversations", json={"title": "artifact"}).json()
        run = client.post(
            f"/api/v1/runs/conversations/{conversation['id']}",
            json={"content": "create artifact"},
        ).json()
        storage_key = f"workspaces/{admin_seed['workspace_id']}/artifacts/{new_id()}/result.txt"
        LocalFileStorage().put_bytes(storage_key, b"artifact result")
        artifact_id = new_id()
        now = utc_now()

        async def persist_artifact():
            db_run = await db_session.get(Run, run["id"])
            db_session.add(
                Artifact(
                    id=artifact_id,
                    workspace_id=admin_seed["workspace_id"],
                    run_id=db_run.id,
                    owner_user_id=admin_seed["user_id"],
                    type="text",
                    name="result.txt",
                    mime_type="text/plain",
                    size=15,
                    storage_key=storage_key,
                    sha256="x" * 64,
                    created_at=now,
                )
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(persist_artifact())
        preview = client.get(f"/api/v1/artifacts/{artifact_id}/preview")
        assert preview.status_code == 200
        assert preview.json()["text"] == "artifact result"
        download = client.get(f"/api/v1/artifacts/{artifact_id}/download")
        assert download.status_code == 200
        assert download.content == b"artifact result"
        assert "attachment" in download.headers["content-disposition"]
    finally:
        settings.local_storage_root = original_root


def test_render_endpoints_create_typed_artifacts(client, admin_seed, tmp_path):
    original_root = settings.local_storage_root
    settings.local_storage_root = tmp_path
    try:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin-password-123"},
            ).status_code
            == 200
        )
        conversation = client.post("/api/v1/conversations", json={"title": "render"}).json()
        run = client.post(
            f"/api/v1/runs/conversations/{conversation['id']}",
            json={"content": "render files"},
        ).json()
        document = client.post(
            f"/api/v1/runs/{run['id']}/render/document",
            json={
                "name": "投标文件.docx",
                "spec": {
                    "title": "投标文件",
                    "sections": [{"title": "项目理解", "paragraphs": ["测试"]}],
                },
            },
        )
        presentation = client.post(
            f"/api/v1/runs/{run['id']}/render/presentation",
            json={"name": "经营汇报.pptx", "spec": {"title": "经营汇报", "slides": []}},
        )
        spreadsheet = client.post(
            f"/api/v1/runs/{run['id']}/render/spreadsheet",
            json={"name": "经营数据.xlsx", "spec": {"sheets": {"Summary": [["Revenue", 100]]}}},
        )
        assert document.status_code == 201
        assert presentation.status_code == 201
        assert spreadsheet.status_code == 201
        assert document.json()["type"] == "document"
        assert presentation.json()["type"] == "presentation"
        assert spreadsheet.json()["type"] == "spreadsheet"
    finally:
        settings.local_storage_root = original_root
