from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.security import (
    digest_token,
    new_session_token,
    utc_now,
)
from backend.app.models.identity import (
    AuthIdentity,
    LocalCredential,
    Session,
    User,
    WorkspaceMember,
)
from backend.app.schemas.auth import UserResponse


def _public_user(user: User, identity: AuthIdentity, credential: LocalCredential) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=identity.username_normalized,
        display_name=user.display_name,
        status=user.status,
        must_change_password=credential.must_change_password,
    )


async def find_local_identity(
    db: AsyncSession, username: str
) -> tuple[User, AuthIdentity, LocalCredential] | None:
    identity = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == "local",
            AuthIdentity.username_normalized == username.strip().lower(),
        )
    )
    if not identity:
        return None
    user = await db.get(User, identity.user_id)
    credential = await db.scalar(
        select(LocalCredential).where(LocalCredential.auth_identity_id == identity.id)
    )
    if not user or not credential:
        return None
    return user, identity, credential


async def workspace_for_user(db: AsyncSession, user_id: str) -> WorkspaceMember | None:
    return await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(WorkspaceMember.created_at)
    )


async def create_session(db: AsyncSession, user: User, credential: LocalCredential) -> str:
    token = new_session_token()
    now = utc_now()
    db.add(
        Session(
            user_id=user.id,
            token_digest=digest_token(token),
            credential_version=credential.credential_version,
            expires_at=now + timedelta(seconds=settings.session_absolute_seconds),
            idle_expires_at=now + timedelta(seconds=settings.session_idle_seconds),
            last_seen_at=now,
        )
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


async def current_user_context(
    request: Request, db: AsyncSession
) -> tuple[User, AuthIdentity, LocalCredential, WorkspaceMember]:
    token = request.cookies.get(settings.session_cookie_name)
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    if not token:
        raise unauthorized
    session = await db.scalar(
        select(Session).where(
            Session.token_digest == digest_token(token),
            Session.revoked_at.is_(None),
        )
    )
    now = utc_now()
    if not session or session.expires_at < now or session.idle_expires_at < now:
        raise unauthorized
    user = await db.get(User, session.user_id)
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == session.user_id))
    credential = await db.scalar(
        select(LocalCredential).where(LocalCredential.auth_identity_id == identity.id)
        if identity
        else select(LocalCredential).where(LocalCredential.id == "")
    )
    membership = await workspace_for_user(db, session.user_id)
    if not user or not identity or not credential or not membership or user.status != "active":
        raise unauthorized
    if session.credential_version != credential.credential_version:
        raise unauthorized
    session.last_seen_at = now
    session.idle_expires_at = now + timedelta(seconds=settings.session_idle_seconds)
    return user, identity, credential, membership


async def require_admin(
    request: Request, db: AsyncSession
) -> tuple[User, AuthIdentity, LocalCredential, WorkspaceMember]:
    context = await current_user_context(request, db)
    if context[3].role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要 Workspace 管理员权限",
        )
    return context


def new_temporary_password() -> str:
    return secrets.token_urlsafe(18)


__all__ = [
    "_public_user",
    "create_session",
    "current_user_context",
    "find_local_identity",
    "new_temporary_password",
    "require_admin",
    "set_session_cookie",
    "workspace_for_user",
]
