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

    members = client.get("/api/v1/admin/users")
    assert members.status_code == 200
    member = next(item for item in members.json() if item["username"] == "member")
    reset = client.post(f"/api/v1/admin/users/{member['id']}/reset-password")
    assert reset.status_code == 200
    assert reset.json()["user"]["must_change_password"] is True
    assert reset.json()["temporary_password"] != created.json()["temporary_password"]
    disabled = client.patch(
        f"/api/v1/admin/users/{member['id']}",
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    last_admin = client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"status": "disabled"},
    )
    assert last_admin.status_code == 409
    audit = client.get("/api/v1/admin/audit-logs")
    assert audit.status_code == 200
    assert any(row["action"] == "user.created" for row in audit.json())


def test_unauthenticated_admin_endpoint_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "member", "display_name": "业务成员", "role": "member"},
    )
    assert response.status_code == 401


def test_login_lockout_after_repeated_failures(client, admin_seed, monkeypatch) -> None:
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "login_max_failures", 2)
    first = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    second = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert first.status_code == 401
    assert second.status_code == 401
    locked = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
    )
    assert locked.status_code == 401


def test_change_password_keeps_current_session_and_invalidates_old_password(
    client, admin_seed
) -> None:
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin-password-123"},
        ).status_code
        == 200
    )
    changed = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "admin-password-123",
            "new_password": "admin-password-456",
        },
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert old_login.status_code == 401


def test_logout_revokes_current_session(client, admin_seed) -> None:
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_production_cookie_uses_host_prefix(client, admin_seed, monkeypatch) -> None:
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
    )
    assert response.status_code == 200
    assert "__Host-company_agent_session" in response.headers.get("set-cookie", "")
