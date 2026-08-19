from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.secrets import SecretManager
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    Connector,
    ConnectorVersion,
    DataSource,
    Plugin,
    PluginVersion,
    SecretRecord,
    Skill,
    SkillVersion,
)
from backend.app.schemas.capabilities import (
    ConnectorResponse,
    ConnectorVersionResponse,
    CreateConnectorRequest,
    CreateDataSourceRequest,
    CreatePluginRequest,
    CreateSecretRequest,
    CreateSkillRequest,
    DataSourceResponse,
    PluginResponse,
    PluginVersionResponse,
    SecretResponse,
    SkillResponse,
    SkillVersionResponse,
)
from backend.app.services.auth import current_user_context

router = APIRouter(tags=["capabilities"])


def _skill(skill: Skill) -> SkillResponse:
    return SkillResponse.model_validate(skill, from_attributes=True)


def _skill_version(version: SkillVersion) -> SkillVersionResponse:
    return SkillVersionResponse.model_validate(version, from_attributes=True)


def _connector(connector: Connector) -> ConnectorResponse:
    return ConnectorResponse.model_validate(connector, from_attributes=True)


def _connector_version(version: ConnectorVersion) -> ConnectorVersionResponse:
    return ConnectorVersionResponse.model_validate(version, from_attributes=True)


def _plugin(plugin: Plugin) -> PluginResponse:
    return PluginResponse.model_validate(plugin, from_attributes=True)


def _plugin_version(version: PluginVersion) -> PluginVersionResponse:
    return PluginVersionResponse.model_validate(version, from_attributes=True)


def _data_source(source) -> DataSourceResponse:
    return DataSourceResponse.model_validate(source, from_attributes=True)


async def _can_edit(owner_id: str, user_id: str, role: str) -> bool:
    return owner_id == user_id or role == "admin"


@router.post("/secrets", response_model=SecretResponse, status_code=status.HTTP_201_CREATED)
async def create_secret(
    payload: CreateSecretRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SecretResponse:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    nonce, ciphertext = SecretManager().encrypt(payload.value)
    now = utc_now()
    record = SecretRecord(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        provider=payload.provider,
        ciphertext=ciphertext,
        nonce=nonce,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    return SecretResponse.model_validate(record, from_attributes=True)


@router.get("/secrets", response_model=list[SecretResponse])
async def list_secrets(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[SecretResponse]:
    _, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(SecretRecord)
        .where(
            SecretRecord.workspace_id == membership.workspace_id, SecretRecord.deleted_at.is_(None)
        )
        .order_by(SecretRecord.created_at.desc())
    )
    return [SecretResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/skills", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: CreateSkillRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    user, _, _, membership = await current_user_context(request, db)
    now = utc_now()
    skill = Skill(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        visibility=payload.visibility,
        created_at=now,
        updated_at=now,
    )
    version = SkillVersion(
        id=new_id(),
        skill_id=skill.id,
        version_number=1,
        status="draft",
        spec=payload.spec,
        created_by=user.id,
        created_at=now,
    )
    db.add_all([skill, version])
    await db.commit()
    return _skill(skill)


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(request: Request, db: AsyncSession = Depends(get_db)) -> list[SkillResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Skill)
        .where(
            Skill.workspace_id == membership.workspace_id,
            (Skill.owner_user_id == user.id) | (Skill.visibility == "workspace"),
            Skill.status == "active",
        )
        .order_by(Skill.updated_at.desc())
    )
    return [_skill(row) for row in rows]


@router.post("/skills/{skill_id}/versions", response_model=SkillVersionResponse)
async def create_skill_version(
    skill_id: str,
    payload: CreateSkillRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SkillVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    skill = await db.scalar(
        select(Skill).where(Skill.id == skill_id, Skill.workspace_id == membership.workspace_id)
    )
    if not skill or not await _can_edit(skill.owner_user_id, user.id, membership.role):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill 不存在或无编辑权限"
        )
    latest = await db.scalar(
        select(func.max(SkillVersion.version_number)).where(SkillVersion.skill_id == skill.id)
    )
    now = utc_now()
    version = SkillVersion(
        id=new_id(),
        skill_id=skill.id,
        version_number=int(latest or 0) + 1,
        based_on_version_id=skill.published_version_id,
        status="draft",
        spec=payload.spec,
        created_by=user.id,
        created_at=now,
    )
    skill.updated_at = now
    db.add(version)
    await db.commit()
    return _skill_version(version)


@router.post("/skill-versions/{version_id}/publish", response_model=SkillVersionResponse)
async def publish_skill_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> SkillVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(SkillVersion, version_id)
    skill = await db.get(Skill, version.skill_id) if version else None
    if not version or not skill or skill.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill Version 不存在")
    if not await _can_edit(skill.owner_user_id, user.id, membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无发布权限")
    if version.status == "published":
        return _skill_version(version)
    if version.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有 Draft 可以发布")
    version.status = "published"
    version.published_at = utc_now()
    skill.published_version_id = version.id
    skill.updated_at = utc_now()
    await db.commit()
    return _skill_version(version)


@router.post("/connectors", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: CreateConnectorRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    now = utc_now()
    connector = Connector(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        provider=payload.provider,
        visibility=payload.visibility,
        created_at=now,
        updated_at=now,
    )
    version = ConnectorVersion(
        id=new_id(),
        connector_id=connector.id,
        version_number=1,
        status="draft",
        spec=payload.spec,
        created_by=user.id,
        created_at=now,
    )
    db.add_all([connector, version])
    await db.commit()
    return _connector(connector)


@router.post(
    "/data-sources",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_data_source(
    payload: CreateDataSourceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    forbidden_keys = {"password", "api_key", "token", "secret", "dsn"}
    if forbidden_keys.intersection(payload.connection_config):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="连接配置只能保存非敏感信息，密码和 Token 必须放入 Secret",
        )
    if payload.secret_id:
        secret = await db.scalar(
            select(SecretRecord).where(
                SecretRecord.id == payload.secret_id,
                SecretRecord.workspace_id == membership.workspace_id,
                SecretRecord.deleted_at.is_(None),
            )
        )
        if not secret:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret 不存在")
    now = utc_now()
    source = DataSource(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        provider=payload.provider,
        connection_config=payload.connection_config,
        secret_id=payload.secret_id,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(source)
    await db.commit()
    return _data_source(source)


@router.get("/data-sources", response_model=list[DataSourceResponse])
async def list_data_sources(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[DataSourceResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(DataSource).where(
            DataSource.workspace_id == membership.workspace_id,
            DataSource.owner_user_id == user.id,
        )
    )
    return [_data_source(row) for row in rows]


@router.get("/connectors", response_model=list[ConnectorResponse])
async def list_connectors(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[ConnectorResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Connector).where(
            Connector.workspace_id == membership.workspace_id,
            (Connector.owner_user_id == user.id) | (Connector.visibility == "workspace"),
            Connector.status == "active",
        )
    )
    return [_connector(row) for row in rows]


@router.post("/connector-versions/{version_id}/publish", response_model=ConnectorVersionResponse)
async def publish_connector_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> ConnectorVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(ConnectorVersion, version_id)
    connector = await db.get(Connector, version.connector_id) if version else None
    if not version or not connector or connector.workspace_id != membership.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connector Version 不存在"
        )
    if membership.role != "admin" and connector.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无发布权限")
    if version.status == "published":
        return _connector_version(version)
    if version.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有 Draft 可以发布")
    version.status = "published"
    version.published_at = utc_now()
    connector.published_version_id = version.id
    connector.updated_at = utc_now()
    await db.commit()
    return _connector_version(version)


@router.post("/plugins", response_model=PluginResponse, status_code=status.HTTP_201_CREATED)
async def create_plugin(
    payload: CreatePluginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginResponse:
    user, _, _, membership = await current_user_context(request, db)
    now = utc_now()
    plugin = Plugin(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        visibility=payload.visibility,
        created_at=now,
        updated_at=now,
    )
    version = PluginVersion(
        id=new_id(),
        plugin_id=plugin.id,
        version_number=1,
        status="draft",
        spec=payload.spec,
        created_by=user.id,
        created_at=now,
    )
    db.add_all([plugin, version])
    await db.commit()
    return _plugin(plugin)


@router.get("/plugins", response_model=list[PluginResponse])
async def list_plugins(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[PluginResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Plugin).where(
            Plugin.workspace_id == membership.workspace_id,
            (Plugin.owner_user_id == user.id) | (Plugin.visibility == "workspace"),
            Plugin.status == "active",
        )
    )
    return [_plugin(row) for row in rows]


@router.post("/plugin-versions/{version_id}/publish", response_model=PluginVersionResponse)
async def publish_plugin_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> PluginVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(PluginVersion, version_id)
    plugin = await db.get(Plugin, version.plugin_id) if version else None
    if not version or not plugin or plugin.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin Version 不存在")
    if membership.role != "admin" and plugin.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无发布权限")
    if version.status == "published":
        return _plugin_version(version)
    if version.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有 Draft 可以发布")
    version.status = "published"
    version.published_at = utc_now()
    plugin.published_version_id = version.id
    plugin.updated_at = utc_now()
    await db.commit()
    return _plugin_version(version)


@router.post(
    "/plugins/{plugin_id}/clone", response_model=PluginResponse, status_code=status.HTTP_201_CREATED
)
async def clone_plugin(
    plugin_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginResponse:
    user, _, _, membership = await current_user_context(request, db)
    source = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            (Plugin.owner_user_id == user.id) | (Plugin.visibility == "workspace"),
        )
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    source_version = (
        await db.get(PluginVersion, source.published_version_id)
        if source.published_version_id
        else None
    )
    now = utc_now()
    clone = Plugin(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=f"{source.name} 副本",
        description=source.description,
        visibility="private",
        created_at=now,
        updated_at=now,
    )
    clone_version = PluginVersion(
        id=new_id(),
        plugin_id=clone.id,
        version_number=1,
        status="draft",
        spec=dict(source_version.spec) if source_version else {},
        created_by=user.id,
        created_at=now,
    )
    db.add_all([clone, clone_version])
    await db.commit()
    return _plugin(clone)


__all__ = ["router"]
