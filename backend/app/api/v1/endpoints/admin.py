from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import hash_password, utc_now
from backend.app.models.capabilities import ModelProbeResult, ModelProfile
from backend.app.models.identity import (
    AuthIdentity,
    LocalCredential,
    OrganizationMember,
    Session,
    User,
    Workspace,
    WorkspaceMember,
)
from backend.app.models.runtime import AuditLog
from backend.app.providers.compatible import agnes_client, siliconflow_client
from backend.app.schemas.auth import (
    AuditLogResponse,
    CreatedUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
)
from backend.app.services.audit import record_audit
from backend.app.services.auth import _public_user, new_temporary_password, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


async def _ensure_model_profiles(db: AsyncSession, workspace_id: str) -> list[ModelProfile]:
    definitions = [
        (
            "reasoning",
            "agnes",
            settings.agnes_model,
            settings.agnes_base_url,
            settings.allow_external_chat,
        ),
        (
            "vision",
            "siliconflow",
            settings.siliconflow_vision_model,
            settings.siliconflow_base_url,
            settings.allow_external_vision,
        ),
        (
            "embedding",
            "siliconflow",
            settings.siliconflow_embedding_model,
            settings.siliconflow_base_url,
            settings.allow_external_embedding,
        ),
    ]
    profiles: list[ModelProfile] = []
    for profile_name, provider, model, endpoint, enabled in definitions:
        profile = await db.scalar(
            select(ModelProfile).where(
                ModelProfile.workspace_id == workspace_id,
                ModelProfile.profile_name == profile_name,
            )
        )
        if not profile:
            now = utc_now()
            profile = ModelProfile(
                id=new_id(),
                workspace_id=workspace_id,
                profile_name=profile_name,
                provider=provider,
                model=model,
                endpoint=endpoint,
                enabled=enabled,
                capabilities_json={},
                status="unprobed",
                created_at=now,
                updated_at=now,
            )
            db.add(profile)
            await db.flush()
        profiles.append(profile)
    return profiles


async def _member_rows(db: AsyncSession, workspace_id: str) -> list[UserResponse]:
    rows = await db.execute(
        select(User, AuthIdentity, LocalCredential, WorkspaceMember)
        .join(AuthIdentity, AuthIdentity.user_id == User.id)
        .join(LocalCredential, LocalCredential.auth_identity_id == AuthIdentity.id)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.created_at)
    )
    return [
        _public_user(user, identity, credential) for user, identity, credential, _ in rows.all()
    ]


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
    await record_audit(
        db,
        workspace_id=workspace.id,
        actor_user_id=admin_user.id,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        metadata={"role": payload.role},
    )
    await db.commit()
    return CreatedUserResponse(
        user=_public_user(user, identity, credential),
        workspace_id=workspace.id,
        temporary_password=temporary_password,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, db: AsyncSession = Depends(get_db)) -> list[UserResponse]:
    _, _, _, membership = await require_admin(request, db)
    return await _member_rows(db, membership.workspace_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    admin_user, _, _, membership = await require_admin(request, db)
    target_membership = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == membership.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    user = await db.get(User, user_id)
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == user_id))
    credential = await db.scalar(
        select(LocalCredential).where(LocalCredential.auth_identity_id == identity.id)
        if identity
        else select(LocalCredential).where(LocalCredential.id == "")
    )
    if not target_membership or not user or not identity or not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    demoting_admin = payload.status == "disabled" or payload.role == "member"
    if demoting_admin and target_membership.role == "admin":
        active_admins = await db.scalar(
            select(func.count(WorkspaceMember.id)).where(
                WorkspaceMember.workspace_id == membership.workspace_id,
                WorkspaceMember.role == "admin",
                WorkspaceMember.user_id != user_id,
                WorkspaceMember.user_id.in_(select(User.id).where(User.status == "active")),
            )
        )
        if int(active_admins or 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="不能停用或降级最后一个管理员",
            )
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.status is not None:
        user.status = payload.status
    if payload.role is not None:
        target_membership.role = payload.role
    user.updated_at = utc_now()
    credential.credential_version += 1
    await db.execute(
        Session.__table__.update().where(Session.user_id == user_id).values(revoked_at=utc_now())
    )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=admin_user.id,
        action="user.updated",
        resource_type="user",
        resource_id=user_id,
        metadata={"status": payload.status, "role": payload.role},
    )
    await db.commit()
    return _public_user(user, identity, credential)


@router.post("/users/{user_id}/reset-password", response_model=CreatedUserResponse)
async def reset_password(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CreatedUserResponse:
    admin_user, _, _, membership = await require_admin(request, db)
    target_membership = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == membership.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    user = await db.get(User, user_id)
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == user_id))
    credential = await db.scalar(
        select(LocalCredential).where(LocalCredential.auth_identity_id == identity.id)
        if identity
        else select(LocalCredential).where(LocalCredential.id == "")
    )
    if not target_membership or not user or not identity or not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    temporary_password = new_temporary_password()
    credential.password_hash = hash_password(temporary_password)
    credential.must_change_password = True
    credential.temporary_password_expires_at = utc_now() + timedelta(hours=24)
    credential.credential_version += 1
    await db.execute(
        Session.__table__.update().where(Session.user_id == user_id).values(revoked_at=utc_now())
    )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=admin_user.id,
        action="user.password_reset",
        resource_type="user",
        resource_id=user_id,
    )
    await db.commit()
    return CreatedUserResponse(
        user=_public_user(user, identity, credential),
        workspace_id=target_membership.workspace_id,
        temporary_password=temporary_password,
    )


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_sessions(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    admin_user, _, _, membership = await require_admin(request, db)
    target = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == membership.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db.execute(
        Session.__table__.update().where(Session.user_id == user_id).values(revoked_at=utc_now())
    )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=admin_user.id,
        action="user.sessions_revoked",
        resource_type="user",
        resource_id=user_id,
    )
    await db.commit()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[AuditLogResponse]:
    _, _, _, membership = await require_admin(request, db)
    rows = await db.scalars(
        select(AuditLog)
        .where(AuditLog.workspace_id == membership.workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    return [AuditLogResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/model-profiles")
async def list_model_profiles(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict]:
    _, _, _, membership = await require_admin(request, db)
    profiles = await _ensure_model_profiles(db, membership.workspace_id)
    await db.commit()
    return [
        {
            "id": item.id,
            "profile": item.profile_name,
            "provider": item.provider,
            "model": item.model,
            "configured": bool(
                settings.agnes_api_key
                if item.profile_name == "reasoning"
                else settings.siliconflow_api_key
            ),
            "enabled": item.enabled,
            "status": item.status,
            "capabilities": item.capabilities_json,
        }
        for item in profiles
    ]


@router.post("/model-profiles/{profile}/probe")
async def probe_model_profile(
    profile: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    user, _, _, membership = await require_admin(request, db)
    profiles = await _ensure_model_profiles(db, membership.workspace_id)
    profile_record = next((item for item in profiles if item.profile_name == profile), None)
    if profile_record is None:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未知 Model Profile")
    try:
        if profile == "reasoning":
            response = await agnes_client().chat(
                model=settings.agnes_model,
                messages=[{"role": "user", "content": "只回复 OK"}],
            )
            detail = {"text": response.text[:100], "model": settings.agnes_model}
        elif profile == "vision":
            response = await siliconflow_client().chat(
                model=settings.siliconflow_vision_model,
                messages=[{"role": "user", "content": "只回复 OK"}],
                enable_thinking=False,
            )
            detail = {"text": response.text[:100], "model": settings.siliconflow_vision_model}
        elif profile == "embedding":
            vectors = await siliconflow_client().embeddings(
                model=settings.siliconflow_embedding_model, inputs=["probe"]
            )
            detail = {
                "dimensions": len(vectors[0]) if vectors else 0,
                "model": settings.siliconflow_embedding_model,
            }
    except HTTPException:
        raise
    except Exception as exc:
        await record_audit(
            db,
            workspace_id=membership.workspace_id,
            actor_user_id=user.id,
            action="model_profile.probe_failed",
            resource_type="model_profile",
            resource_id=profile,
            metadata={"error": type(exc).__name__},
        )
        profile_record.status = "failed"
        profile_record.updated_at = utc_now()
        db.add(
            ModelProbeResult(
                id=new_id(),
                workspace_id=membership.workspace_id,
                profile_id=profile_record.id,
                status="failed",
                details_json={},
                error_code=type(exc).__name__,
                created_at=utc_now(),
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=type(exc).__name__
        ) from exc
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="model_profile.probed",
        resource_type="model_profile",
        resource_id=profile,
        metadata=detail,
    )
    profile_record.status = "ready"
    profile_record.capabilities_json = detail
    profile_record.updated_at = utc_now()
    db.add(
        ModelProbeResult(
            id=new_id(),
            workspace_id=membership.workspace_id,
            profile_id=profile_record.id,
            status="ready",
            details_json=detail,
            created_at=utc_now(),
        )
    )
    await db.commit()
    return {"profile": profile, "profile_id": profile_record.id, "status": "ready", **detail}


__all__ = ["router"]
