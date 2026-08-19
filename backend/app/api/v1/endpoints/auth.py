from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import digest_token, hash_password, utc_now, verify_password
from backend.app.models.identity import Session
from backend.app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserResponse,
)
from backend.app.services.auth import (
    _public_user,
    create_session,
    current_user_context,
    find_local_identity,
    session_cookie_name,
    set_session_cookie,
    workspace_for_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    context = await find_local_identity(db, payload.username)
    if not context:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    user, identity, credential = context
    now = utc_now()
    if (
        credential.locked_until
        and credential.locked_until > now
        or credential.must_change_password
        and credential.temporary_password_expires_at
        and credential.temporary_password_expires_at <= now
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    if user.status != "active" or not verify_password(credential.password_hash, payload.password):
        credential.failed_attempt_count += 1
        if credential.failed_attempt_count >= settings.login_max_failures:
            credential.locked_until = now + timedelta(seconds=settings.login_lockout_seconds)
            credential.failed_attempt_count = 0
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    credential.failed_attempt_count = 0
    credential.locked_until = None
    membership = await workspace_for_user(db, user.id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号尚未加入 Workspace")
    token = await create_session(db, user, credential)
    await db.commit()
    set_session_cookie(response, token)
    return LoginResponse(
        user=_public_user(user, identity, credential),
        workspace_id=membership.workspace_id,
        requires_password_change=credential.must_change_password,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:

    token = request.cookies.get(session_cookie_name())
    if token:
        from backend.app.core.security import digest_token

        session = await db.scalar(
            select(Session).where(Session.token_digest == digest_token(token))
        )
        if session:
            session.revoked_at = utc_now()
            await db.commit()
    response.delete_cookie(session_cookie_name(), path="/")


@router.get("/me", response_model=UserResponse)
async def me(request: Request, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user, identity, credential, _ = await current_user_context(request, db)
    return _public_user(user, identity, credential)


@router.post("/change-password", response_model=UserResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user, identity, credential, _ = await current_user_context(request, db)
    if not verify_password(credential.password_hash, payload.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码不正确")
    credential.password_hash = hash_password(payload.new_password)
    credential.must_change_password = False
    credential.password_changed_at = utc_now()
    credential.credential_version += 1
    token = request.cookies.get(session_cookie_name())
    if token:
        session = await db.scalar(
            select(Session).where(Session.token_digest == digest_token(token))
        )
        if session:
            session.revoked_at = utc_now()
    new_token = await create_session(db, user, credential)
    await db.commit()
    set_session_cookie(response, new_token)
    return _public_user(user, identity, credential)


__all__ = ["router"]
