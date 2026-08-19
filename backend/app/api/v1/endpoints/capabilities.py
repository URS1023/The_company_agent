from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.secrets import SecretManager
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    CapabilityTestRun,
    Connector,
    ConnectorVersion,
    DataSource,
    Plugin,
    PluginResourceBinding,
    PluginSkillBinding,
    PluginToolBinding,
    PluginVersion,
    SecretRecord,
    Skill,
    SkillVersion,
)
from backend.app.schemas.capabilities import (
    CapabilityTestRunResponse,
    ConnectorResponse,
    ConnectorVersionResponse,
    CreateConnectorRequest,
    CreateDataSourceRequest,
    CreatePluginRequest,
    CreateSecretRequest,
    CreateSkillRequest,
    DataSourceResponse,
    PluginBindingRequest,
    PluginResponse,
    PluginVersionResponse,
    SecretResponse,
    SkillResponse,
    SkillVersionResponse,
    ToolInvocationRequest,
    ToolTestResponse,
)
from backend.app.services.auth import current_user_context
from backend.app.services.connectors import test_database_connection, test_http_connector

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


async def _has_passed_test(
    db: AsyncSession, workspace_id: str, resource_type: str, resource_version_id: str
) -> bool:
    return bool(
        await db.scalar(
            select(CapabilityTestRun.id).where(
                CapabilityTestRun.workspace_id == workspace_id,
                CapabilityTestRun.resource_type == resource_type,
                CapabilityTestRun.resource_version_id == resource_version_id,
                CapabilityTestRun.status == "passed",
            )
        )
    )


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
    if not await _has_passed_test(db, membership.workspace_id, "skill", version.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Skill 必须先通过 Test Run",
        )
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


@router.post("/connector-versions/{version_id}/test-invocation", response_model=ToolTestResponse)
async def test_connector_invocation(
    version_id: str,
    payload: ToolInvocationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ToolTestResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(ConnectorVersion, version_id)
    connector = await db.get(Connector, version.connector_id) if version else None
    if not version or not connector or connector.workspace_id != membership.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector Version 不存在",
        )
    if connector.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无测试权限")
    if connector.provider != "http":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="当前端点只测试 HTTP Connector",
        )
    try:
        result = await test_http_connector(version, payload.arguments)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=type(exc).__name__,
        ) from exc
    return ToolTestResponse(**result)


@router.post("/data-sources/{source_id}/test-connection", response_model=ToolTestResponse)
async def test_source_connection(
    source_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ToolTestResponse:
    user, _, _, membership = await current_user_context(request, db)
    source = await db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.workspace_id == membership.workspace_id,
        )
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DataSource 不存在")
    if source.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无测试权限")
    secret = await db.get(SecretRecord, source.secret_id) if source.secret_id else None
    try:
        result = await test_database_connection(source, secret)
    except Exception as exc:
        source.status = "error"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=type(exc).__name__,
        ) from exc
    source.status = "ready"
    await db.commit()
    return ToolTestResponse(**result)


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
    if not await _has_passed_test(db, membership.workspace_id, "connector", version.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connector 必须先通过 Test Run",
        )
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
    if not await _has_passed_test(db, membership.workspace_id, "plugin", version.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plugin 必须先通过 Test Run",
        )
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


async def _create_capability_test(
    *,
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    resource_type: str,
    resource_version_id: str,
    spec: dict,
) -> CapabilityTestRun:
    now = utc_now()
    status_value = "passed" if isinstance(spec, dict) else "failed"
    output = {
        "validated": status_value == "passed",
        "spec_keys": sorted(spec.keys()) if isinstance(spec, dict) else [],
    }
    result = CapabilityTestRun(
        id=new_id(),
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_version_id=resource_version_id,
        status=status_value,
        input_json=spec if isinstance(spec, dict) else {},
        output_json=output,
        error_summary=None if status_value == "passed" else "Spec 必须是对象",
        created_by=user_id,
        created_at=now,
    )
    db.add(result)
    await db.commit()
    return result


def _test_response(result: CapabilityTestRun) -> CapabilityTestRunResponse:
    return CapabilityTestRunResponse.model_validate(result, from_attributes=True)


@router.post("/skill-versions/{version_id}/test-runs", response_model=CapabilityTestRunResponse)
async def test_skill_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> CapabilityTestRunResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(SkillVersion, version_id)
    skill = await db.get(Skill, version.skill_id) if version else None
    if not version or not skill or skill.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill Version 不存在")
    if skill.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无 Test Run 权限")
    result = await _create_capability_test(
        db=db,
        workspace_id=membership.workspace_id,
        user_id=user.id,
        resource_type="skill",
        resource_version_id=version.id,
        spec=version.spec,
    )
    return _test_response(result)


@router.post("/connector-versions/{version_id}/test-runs", response_model=CapabilityTestRunResponse)
async def test_connector_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> CapabilityTestRunResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(ConnectorVersion, version_id)
    connector = await db.get(Connector, version.connector_id) if version else None
    if not version or not connector or connector.workspace_id != membership.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector Version 不存在",
        )
    if connector.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无 Test Run 权限")
    result = await _create_capability_test(
        db=db,
        workspace_id=membership.workspace_id,
        user_id=user.id,
        resource_type="connector",
        resource_version_id=version.id,
        spec=version.spec,
    )
    return _test_response(result)


@router.post("/plugin-versions/{version_id}/test-runs", response_model=CapabilityTestRunResponse)
async def test_plugin_version(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> CapabilityTestRunResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(PluginVersion, version_id)
    plugin = await db.get(Plugin, version.plugin_id) if version else None
    if not version or not plugin or plugin.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin Version 不存在")
    if plugin.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无 Test Run 权限")
    result = await _create_capability_test(
        db=db,
        workspace_id=membership.workspace_id,
        user_id=user.id,
        resource_type="plugin",
        resource_version_id=version.id,
        spec=version.spec,
    )
    return _test_response(result)


@router.post("/plugin-versions/{version_id}/bindings", status_code=status.HTTP_204_NO_CONTENT)
async def bind_plugin_version(
    version_id: str,
    payload: PluginBindingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(PluginVersion, version_id)
    plugin = await db.get(Plugin, version.plugin_id) if version else None
    if not version or not plugin or plugin.workspace_id != membership.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin Version 不存在")
    if version.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有 Draft 可以修改绑定")
    if plugin.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无绑定权限")
    skills = list(
        await db.scalars(
            select(SkillVersion)
            .join(Skill)
            .where(
                SkillVersion.id.in_(payload.skill_version_ids),
                Skill.workspace_id == membership.workspace_id,
            )
        )
    )
    connectors = list(
        await db.scalars(
            select(ConnectorVersion)
            .join(Connector)
            .where(
                ConnectorVersion.id.in_(payload.connector_version_ids),
                Connector.workspace_id == membership.workspace_id,
            )
        )
    )
    if len(skills) != len(set(payload.skill_version_ids)) or len(connectors) != len(
        set(payload.connector_version_ids)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="绑定对象不存在或不属于当前 Workspace",
        )
    for skill_version in skills:
        db.add(
            PluginSkillBinding(
                id=new_id(), plugin_version_id=version.id, skill_version_id=skill_version.id
            )
        )
    for connector_version in connectors:
        db.add(
            PluginToolBinding(
                id=new_id(),
                plugin_version_id=version.id,
                connector_version_id=connector_version.id,
            )
        )
    for resource in payload.resources:
        resource_type = resource.get("type")
        resource_id = resource.get("id")
        if not resource_type or not resource_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Resource binding 缺少 type/id",
            )
        db.add(
            PluginResourceBinding(
                id=new_id(),
                plugin_version_id=version.id,
                resource_type=resource_type,
                resource_id=resource_id,
                config={},
            )
        )
    await db.commit()


__all__ = ["router"]
