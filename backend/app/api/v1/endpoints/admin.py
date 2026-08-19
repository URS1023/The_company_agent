from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import hash_password, utc_now
from backend.app.models.identity import (
    AuthIdentity,
    LocalCredential,
    OrganizationMember,
    User,
    Workspace,
    WorkspaceMember,
)
from backend.app.schemas.auth import CreatedUserResponse, CreateUserRequest
from backend.app.services.auth import _public_user, new_temporary_password, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/users", response_model=CreatedUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CreatedUserResponse:
    admin_user, _, _, membership = await require_admin(request, db)
    username = payload.username.strip().lower()
    existing = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == "local", AuthIdentity.username_normalized == username
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在")
    workspace = await db.get(Workspace, membership.workspace_id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace 不存在")
    now = utc_now()
    temporary_password = new_temporary_password()
    user = User(
        id=new_id(),
        display_name=payload.display_name.strip(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    identity = AuthIdentity(
        id=new_id(),
        user_id=user.id,
        provider="local",
        username_normalized=username,
        created_at=now,
    )
    credential = LocalCredential(
        id=new_id(),
        auth_identity_id=identity.id,
        password_hash=hash_password(temporary_password),
        must_change_password=True,
        temporary_password_expires_at=now + timedelta(hours=24),
        password_changed_at=None,
    )
    db.add_all(
        [
            user,
            identity,
            credential,
            OrganizationMember(
                id=new_id(),
                organization_id=workspace.organization_id,
                user_id=user.id,
                role=payload.role,
                created_at=now,
            ),
            WorkspaceMember(
                id=new_id(),
                workspace_id=workspace.id,
                user_id=user.id,
                role=payload.role,
                created_at=now,
            ),
        ]
    )
    await db.commit()
    return CreatedUserResponse(
        user=_public_user(user, identity, credential),
        workspace_id=workspace.id,
        temporary_password=temporary_password,
    )


__all__ = ["router"]
