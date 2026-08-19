from __future__ import annotations

import asyncio

from backend.app.core.config import settings
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Conversation, Run
from backend.app.services.artifacts import persist_artifact


def test_persist_artifact_writes_storage_and_run_event(db_session, admin_seed, tmp_path) -> None:
    original_root = settings.local_storage_root
    settings.local_storage_root = tmp_path
    try:
        now = utc_now()
        conversation = Conversation(
            id=new_id(),
            workspace_id=admin_seed["workspace_id"],
            owner_user_id=admin_seed["user_id"],
            title="artifact service",
            created_at=now,
            updated_at=now,
        )
        run = Run(
            id=new_id(),
            workspace_id=admin_seed["workspace_id"],
            conversation_id=conversation.id,
            started_by_user_id=admin_seed["user_id"],
            status="running",
            created_at=now,
        )
        db_session.add_all([conversation, run])

        async def persist():
            await db_session.flush()
            artifact = await persist_artifact(
                db_session,
                run=run,
                owner_user_id=admin_seed["user_id"],
                artifact_type="document",
                name="result.txt",
                mime_type="text/plain",
                content=b"result",
            )
            await db_session.commit()
            return artifact

        artifact = asyncio.get_event_loop().run_until_complete(persist())
        assert artifact.size == 6
        assert artifact.storage_key
        assert len(artifact.sha256) == 64
    finally:
        settings.local_storage_root = original_root
