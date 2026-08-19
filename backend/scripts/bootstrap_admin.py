from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from backend.app.core.database import Base, SessionLocal, engine
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


async def bootstrap(username: str, display_name: str, password: str) -> None:
    if len(password) < 12:
        raise ValueError("admin password must contain at least 12 characters")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = utc_now()
    async with SessionLocal.begin() as session:
        existing = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.username_normalized == username.strip().lower(),
            )
        )
        if existing:
            raise ValueError("an account with this username already exists")
        organization = Organization(name="默认组织", created_at=now)
        workspace = Workspace(organization_id=organization.id, name="默认工作区", created_at=now)
        user = User(display_name=display_name, created_at=now, updated_at=now)
        identity = AuthIdentity(
            user_id=user.id,
            provider="local",
            username_normalized=username.strip().lower(),
            created_at=now,
        )
        credential = LocalCredential(
            auth_identity_id=identity.id,
            password_hash=hash_password(password),
            must_change_password=False,
            password_changed_at=now,
        )
        session.add_all(
            [
                organization,
                workspace,
                user,
                identity,
                credential,
                OrganizationMember(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="admin",
                    created_at=now,
                ),
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="admin",
                    created_at=now,
                ),
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first local administrator.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", default="系统管理员")
    args = parser.parse_args()
    password = getpass.getpass("Admin password (12+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match", file=sys.stderr)
        return 2
    try:
        asyncio.run(bootstrap(args.username, args.display_name, password))
    except Exception as exc:  # pragma: no cover - environment-specific
        print(f"Bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Created administrator account: {args.username}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
