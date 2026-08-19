from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import models  # noqa: F401 - register all model metadata
from backend.app.core.database import Base, get_db
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


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_seed(db_session):
    now = utc_now()
    organization = Organization(id=new_id(), name="测试组织", created_at=now)
    workspace = Workspace(
        id=new_id(), organization_id=organization.id, name="测试工作区", created_at=now
    )
    admin = User(
        id=new_id(),
        display_name="管理员",
        status="active",
        created_at=now,
        updated_at=now,
    )
    identity = AuthIdentity(
        id=new_id(),
        user_id=admin.id,
        provider="local",
        username_normalized="admin",
        created_at=now,
    )
    credential = LocalCredential(
        id=new_id(),
        auth_identity_id=identity.id,
        password_hash=hash_password("admin-password-123"),
        must_change_password=False,
        password_changed_at=now,
    )
    db_session.add_all(
        [
            organization,
            workspace,
            admin,
            identity,
            credential,
            OrganizationMember(
                id=new_id(),
                organization_id=organization.id,
                user_id=admin.id,
                role="admin",
                created_at=now,
            ),
            WorkspaceMember(
                id=new_id(),
                workspace_id=workspace.id,
                user_id=admin.id,
                role="admin",
                created_at=now,
            ),
        ]
    )
    asyncio.get_event_loop().run_until_complete(db_session.commit())
    return {"organization_id": organization.id, "workspace_id": workspace.id, "user_id": admin.id}
