from __future__ import annotations

import asyncio

import uvicorn
from sqlalchemy import select

from backend.app.core.database import Base, SessionLocal, engine
from backend.app.core.ids import new_id
from backend.app.core.security import hash_password, utc_now
from backend.app.main import app
from backend.app.models.identity import (
    AuthIdentity,
    LocalCredential,
    Organization,
    OrganizationMember,
    User,
    Workspace,
    WorkspaceMember,
)


async def seed() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal.begin() as db:
        existing = await db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.username_normalized == "workspace-admin",
            )
        )
        if existing:
            return
        now = utc_now()
        organization = Organization(id=new_id(), name="E2E 组织", created_at=now)
        workspace = Workspace(
            id=new_id(), organization_id=organization.id, name="E2E 工作区", created_at=now
        )
        user = User(
            id=new_id(),
            display_name="E2E 管理员",
            status="active",
            created_at=now,
            updated_at=now,
        )
        identity = AuthIdentity(
            id=new_id(),
            user_id=user.id,
            provider="local",
            username_normalized="workspace-admin",
            created_at=now,
        )
        credential = LocalCredential(
            id=new_id(),
            auth_identity_id=identity.id,
            password_hash=hash_password("e2e-admin-password-123"),
            must_change_password=False,
            password_changed_at=now,
        )
        db.add_all(
            [
                organization,
                workspace,
                user,
                identity,
                credential,
                OrganizationMember(
                    id=new_id(),
                    organization_id=organization.id,
                    user_id=user.id,
                    role="admin",
                    created_at=now,
                ),
                WorkspaceMember(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="admin",
                    created_at=now,
                ),
            ]
        )


if __name__ == "__main__":
    asyncio.run(seed())
    uvicorn.run(app, host="127.0.0.1", port=8000)
