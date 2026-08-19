from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.models.runtime import OutboxEvent


def test_knowledge_base_keeps_uploaded_file_as_explicit_document(
    client, db_session, admin_seed, tmp_path
) -> None:
    from backend.app.core.config import settings

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
        knowledge_base = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "招投标资料", "visibility": "private"},
        )
        assert knowledge_base.status_code == 201
        base_id = knowledge_base.json()["id"]
        uploaded = client.post(
            "/api/v1/files",
            files={"upload": ("资质.txt", "ISO9001\n历史项目".encode(), "text/plain")},
        )
        assert uploaded.status_code == 201
        file_id = uploaded.json()["id"]
        added = client.post(
            f"/api/v1/knowledge-bases/{base_id}/documents",
            json={"file_id": file_id},
        )
        assert added.status_code == 202
        assert added.json()["status"] == "queued"

        async def read_outbox():
            return list(
                await db_session.scalars(
                    select(OutboxEvent).where(OutboxEvent.topic == "knowledge.document.created")
                )
            )

        outbox = asyncio.get_event_loop().run_until_complete(read_outbox())
        assert outbox
        assert outbox[-1].payload["file_id"] == file_id
    finally:
        settings.local_storage_root = original_root
