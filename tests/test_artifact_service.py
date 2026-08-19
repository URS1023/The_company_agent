from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.capabilities import ArtifactLineage
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
            source = await persist_artifact(
                db_session,
                run=run,
                owner_user_id=admin_seed["user_id"],
                artifact_type="document",
                name="source.txt",
                mime_type="text/plain",
                content=b"result",
            )
            derived = await persist_artifact(
                db_session,
                run=run,
                owner_user_id=admin_seed["user_id"],
                artifact_type="document",
                name="derived.txt",
                mime_type="text/plain",
                content=b"derived",
                parent_artifact_id=source.id,
            )
            await db_session.commit()
            lineage = await db_session.scalar(
                select(ArtifactLineage).where(ArtifactLineage.artifact_id == derived.id)
            )
            return source, derived, lineage

        source, derived, lineage = asyncio.get_event_loop().run_until_complete(persist())
        assert source.size == 6
        assert derived.storage_key
        assert len(derived.sha256) == 64
        assert lineage is not None
        assert lineage.parent_artifact_id == source.id
    finally:
        settings.local_storage_root = original_root
