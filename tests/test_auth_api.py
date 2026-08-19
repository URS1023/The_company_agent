from __future__ import annotations

from backend.app.core.ids import new_id
from backend.app.core.security import hash_password, utc_now
from backend.app.models.identity import (
    AuthIdentity,
    LocalCredential,
    Organization,
    OrganizationMember,
    User,
    Workspace,
    WorkspaceMember,
)


def test_admin_can_login_and_create_member(client, db_session) -> None:
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
    import asyncio

    asyncio.get_event_loop().run_until_complete(db_session.commit())

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["workspace_id"] == workspace.id
    assert login.cookies

    created = client.post(
        "/api/v1/admin/users",
        json={"username": "member", "display_name": "业务成员", "role": "member"},
    )
    assert created.status_code == 201
    assert created.json()["user"]["must_change_password"] is True
    assert len(created.json()["temporary_password"]) >= 12


def test_unauthenticated_admin_endpoint_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "member", "display_name": "业务成员", "role": "member"},
    )
    assert response.status_code == 401
