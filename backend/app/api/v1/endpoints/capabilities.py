from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.secrets import SecretManager, assert_no_inline_secrets
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    Artifact,
    CapabilityTestRun,
    Connector,
    ConnectorToolBinding,
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
    Tool,
    ToolVersion,
)
from backend.app.models.files import FileAsset
from backend.app.models.knowledge import KnowledgeBase
from backend.app.models.runtime import Conversation, Message, Run
from backend.app.schemas.capabilities import (
    CapabilityTestRunResponse,
    ConnectorBuilderRequest,
    ConnectorBuilderResponse,
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
    PluginRunRequest,
    PluginVersionResponse,
    SecretResponse,
    ShareRequest,
    SkillResponse,
    SkillVersionResponse,
    ToolInvocationRequest,
    ToolResponse,
    ToolTestResponse,
    UpdateDataSourceRequest,
    UpdatePluginRequest,
    UpdateSecretRequest,
    UpdateSkillRequest,
    UpdateToolRequest,
    VersionSpecRequest,
)
from backend.app.services.audit import record_audit
from backend.app.services.auth import current_user_context
from backend.app.services.connector_builder import build_connector_spec
from backend.app.services.connectors import (
    invoke_database_tool,
    test_database_connection,
    test_http_connector,
)
from backend.app.services.runtime import (
    append_outbox_event,
    append_run_event,
    next_message_sequence,
)
from backend.app.tools.http import validate_target
from backend.app.tools.mcp import StreamableHttpMcpClient

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


def _safe_spec(spec: dict) -> dict:
    try:
        assert_no_inline_secrets(spec)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return spec


def _tool(tool: Tool) -> ToolResponse:
    return ToolResponse.model_validate(tool, from_attributes=True)


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
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="secret.created",
        resource_type="secret",
        resource_id=record.id,
        metadata={"provider": record.provider},
    )
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


@router.patch("/secrets/{secret_id}", response_model=SecretResponse)
async def update_secret(
    secret_id: str,
    payload: UpdateSecretRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SecretResponse:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    record = await db.scalar(
        select(SecretRecord).where(
            SecretRecord.id == secret_id,
            SecretRecord.workspace_id == membership.workspace_id,
            SecretRecord.deleted_at.is_(None),
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret 不存在")
    if payload.value is not None:
        record.nonce, record.ciphertext = SecretManager().encrypt(payload.value)
        record.key_version += 1
    if payload.status is not None:
        record.status = payload.status
    record.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="secret.updated",
        resource_type="secret",
        resource_id=record.id,
        metadata={"status": record.status, "rotated": payload.value is not None},
    )
    await db.commit()
    return SecretResponse.model_validate(record, from_attributes=True)


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_secret(
    secret_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    record = await db.scalar(
        select(SecretRecord).where(
            SecretRecord.id == secret_id,
            SecretRecord.workspace_id == membership.workspace_id,
            SecretRecord.deleted_at.is_(None),
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret 不存在")
    record.status = "revoked"
    record.deleted_at = utc_now()
    record.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="secret.revoked",
        resource_type="secret",
        resource_id=record.id,
    )
    await db.commit()


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
        spec=_safe_spec(payload.spec),
        created_by=user.id,
        created_at=now,
    )
    db.add_all([skill, version])
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="skill.created",
        resource_type="skill",
        resource_id=skill.id,
    )
    await db.commit()
    return _skill(skill)


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(request: Request, db: AsyncSession = Depends(get_db)) -> list[SkillResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Skill)
        .where(
            Skill.workspace_id == membership.workspace_id,
            (Skill.owner_user_id == user.id)
            | (Skill.visibility == "workspace")
            | (membership.role == "admin"),
            Skill.status == "active",
        )
        .order_by(Skill.updated_at.desc())
    )
    return [_skill(row) for row in rows]


@router.get("/skills/{skill_id}/versions", response_model=list[SkillVersionResponse])
async def list_skill_versions(
    skill_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[SkillVersionResponse]:
    user, _, _, membership = await current_user_context(request, db)
    skill = await db.scalar(
        select(Skill).where(
            Skill.id == skill_id,
            Skill.workspace_id == membership.workspace_id,
            (Skill.owner_user_id == user.id)
            | (Skill.visibility == "workspace")
            | (membership.role == "admin"),
        )
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill 不存在")
    rows = await db.scalars(
        select(SkillVersion)
        .where(SkillVersion.skill_id == skill.id)
        .order_by(SkillVersion.version_number.desc())
    )
    return [_skill_version(row) for row in rows]


@router.patch("/skills/{skill_id}", response_model=SkillResponse)
async def archive_or_update_skill(
    skill_id: str,
    payload: UpdateSkillRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    user, _, _, membership = await current_user_context(request, db)
    skill = await db.scalar(
        select(Skill).where(
            Skill.id == skill_id,
            Skill.workspace_id == membership.workspace_id,
            Skill.owner_user_id == user.id,
        )
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill 不存在")
    if payload.name is not None:
        skill.name = payload.name.strip() or skill.name
    if payload.description is not None:
        skill.description = payload.description.strip()
    if payload.visibility is not None:
        skill.visibility = payload.visibility
    if payload.spec is not None:
        latest = await db.scalar(
            select(func.max(SkillVersion.version_number)).where(SkillVersion.skill_id == skill.id)
        )
        db.add(
            SkillVersion(
                id=new_id(),
                skill_id=skill.id,
                version_number=int(latest or 0) + 1,
                based_on_version_id=skill.published_version_id,
                status="draft",
                spec=_safe_spec(payload.spec),
                created_by=user.id,
                created_at=utc_now(),
            )
        )
    skill.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="skill.updated",
        resource_type="skill",
        resource_id=skill.id,
    )
    await db.commit()
    return _skill(skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> None:
    user, _, _, membership = await current_user_context(request, db)
    skill = await db.scalar(
        select(Skill).where(
            Skill.id == skill_id,
            Skill.workspace_id == membership.workspace_id,
            Skill.owner_user_id == user.id,
        )
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill 不存在")
    skill.status = "archived"
    skill.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="skill.archived",
        resource_type="skill",
        resource_id=skill.id,
    )
    await db.commit()


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
        spec=_safe_spec(payload.spec),
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
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="skill.published",
        resource_type="skill_version",
        resource_id=version.id,
    )
    await db.commit()
    return _skill_version(version)


@router.post("/skills/{skill_id}/rollback/{version_id}", response_model=SkillVersionResponse)
async def rollback_skill(
    skill_id: str,
    version_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SkillVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    skill = await db.scalar(
        select(Skill).where(
            Skill.id == skill_id,
            Skill.workspace_id == membership.workspace_id,
            Skill.owner_user_id == user.id,
        )
    )
    source = await db.scalar(
        select(SkillVersion).where(
            SkillVersion.id == version_id,
            SkillVersion.skill_id == skill_id,
            SkillVersion.status == "published",
        )
    )
    if not skill or not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill Version 不存在")
    latest = await db.scalar(
        select(func.max(SkillVersion.version_number)).where(SkillVersion.skill_id == skill.id)
    )
    draft = SkillVersion(
        id=new_id(),
        skill_id=skill.id,
        version_number=int(latest or 0) + 1,
        based_on_version_id=source.id,
        status="draft",
        spec=dict(source.spec or {}),
        created_by=user.id,
        created_at=utc_now(),
    )
    db.add(draft)
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="skill.rollback_draft_created",
        resource_type="skill_version",
        resource_id=draft.id,
        metadata={"based_on_version_id": source.id},
    )
    await db.commit()
    return _skill_version(draft)


@router.post("/connectors", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: CreateConnectorRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    user, _, _, membership = await current_user_context(request, db)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    connector_spec = _safe_spec(dict(payload.spec))
    if (
        payload.provider == "mcp"
        and connector_spec.get("endpoint")
        and not connector_spec.get("tools")
    ):
        try:
            endpoint = validate_target(
                str(connector_spec["endpoint"]),
                allow_private=bool(connector_spec.get("allow_private", False)),
            )
            mcp_client = StreamableHttpMcpClient(endpoint)
            await mcp_client.initialize()
            connector_spec["tools"] = await mcp_client.list_tools()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"MCP tools discovery failed: {type(exc).__name__}",
            ) from exc
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
        spec=_safe_spec(connector_spec),
        created_by=user.id,
        created_at=now,
    )
    db.add_all([connector, version])
    for tool_spec in connector_spec.get("tools", []):
        if not isinstance(tool_spec, dict) or not tool_spec.get("name"):
            continue
        tool = Tool(
            id=new_id(),
            workspace_id=membership.workspace_id,
            connector_id=connector.id,
            name=str(tool_spec["name"]),
            description=str(tool_spec.get("description", "")),
            created_at=now,
            updated_at=now,
        )
        tool_version = ToolVersion(
            id=new_id(),
            tool_id=tool.id,
            connector_version_id=version.id,
            version_number=1,
            status="draft",
            spec=tool_spec,
            created_by=user.id,
            created_at=now,
        )
        db.add_all(
            [
                tool,
                tool_version,
                ConnectorToolBinding(
                    id=new_id(),
                    connector_version_id=version.id,
                    tool_version_id=tool_version.id,
                ),
            ]
        )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="connector.created",
        resource_type="connector",
        resource_id=connector.id,
        metadata={"provider": connector.provider},
    )
    await db.commit()
    response = _connector(connector)
    response.draft_version_id = version.id
    return response


@router.post("/connectors/preview", response_model=ConnectorBuilderResponse)
async def preview_connector_spec(
    payload: ConnectorBuilderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConnectorBuilderResponse:
    await current_user_context(request, db)
    spec = build_connector_spec(
        name=payload.name,
        description=payload.description,
        provider=payload.provider,
        base_url=payload.base_url,
        path=payload.path,
        method=payload.method,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
    )
    warnings = []
    if payload.provider in {"http", "mcp"} and not payload.base_url:
        warnings.append("尚未提供 endpoint/base_url，保存前必须补齐")
    warnings.append("Secret 只能保存为 secret_id 引用，不能写入此 Draft Spec")
    return ConnectorBuilderResponse(spec=spec, warnings=warnings)


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
        visibility=payload.visibility,
        connection_config=payload.connection_config,
        secret_id=payload.secret_id,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(source)
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="data_source.created",
        resource_type="data_source",
        resource_id=source.id,
        metadata={"provider": source.provider, "visibility": source.visibility},
    )
    await db.commit()
    return _data_source(source)


@router.patch("/data-sources/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    source_id: str,
    payload: UpdateDataSourceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    user, _, _, membership = await current_user_context(request, db)
    source = await db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.workspace_id == membership.workspace_id,
            DataSource.status != "archived",
        )
    )
    if not source or (source.owner_user_id != user.id and membership.role != "admin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DataSource 不存在或无权限"
        )
    if payload.connection_config is not None:
        forbidden_keys = {"password", "api_key", "token", "secret", "dsn"}
        if forbidden_keys.intersection(payload.connection_config):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="连接配置只能保存非敏感信息，密码和 Token 必须放入 Secret",
            )
        source.connection_config = payload.connection_config
    if payload.secret_id is not None:
        secret = await db.scalar(
            select(SecretRecord).where(
                SecretRecord.id == payload.secret_id,
                SecretRecord.workspace_id == membership.workspace_id,
                SecretRecord.deleted_at.is_(None),
            )
        )
        if not secret:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret 不存在")
        source.secret_id = payload.secret_id
    if payload.name is not None:
        source.name = payload.name.strip() or source.name
    if payload.visibility is not None:
        source.visibility = payload.visibility
    source.status = "draft"
    source.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="data_source.updated",
        resource_type="data_source",
        resource_id=source.id,
    )
    await db.commit()
    return _data_source(source)


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    source = await db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.workspace_id == membership.workspace_id,
            DataSource.status != "archived",
        )
    )
    if not source or (source.owner_user_id != user.id and membership.role != "admin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DataSource 不存在或无权限"
        )
    source.status = "archived"
    source.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="data_source.archived",
        resource_type="data_source",
        resource_id=source.id,
    )
    await db.commit()


@router.get("/data-sources", response_model=list[DataSourceResponse])
async def list_data_sources(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[DataSourceResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(DataSource).where(
            DataSource.workspace_id == membership.workspace_id,
            (DataSource.owner_user_id == user.id)
            | (DataSource.visibility == "workspace")
            | (membership.role == "admin"),
            DataSource.status != "archived",
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
    if connector.provider not in {"http", "mcp"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="当前端点只测试 HTTP/MCP Connector",
        )
    secret = None
    secret_id = (version.spec or {}).get("secret_id")
    if secret_id:
        secret = await db.scalar(
            select(SecretRecord).where(
                SecretRecord.id == secret_id,
                SecretRecord.workspace_id == membership.workspace_id,
                SecretRecord.deleted_at.is_(None),
            )
        )
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Connector Secret 不存在"
            )
    try:
        if connector.provider == "mcp":
            spec = version.spec or {}
            endpoint = validate_target(
                str(spec.get("endpoint", "")),
                allow_private=bool(spec.get("allow_private", False)),
            )
            mcp_client = StreamableHttpMcpClient(endpoint)
            await mcp_client.initialize()
            tool_name = payload.tool_name or spec.get("name")
            if not tool_name:
                tool_name = ((spec.get("tools") or [{}])[0]).get("name")
            if not tool_name:
                raise ValueError("MCP Connector 没有可调用 Tool")
            raw_result = await mcp_client.call_tool(str(tool_name), payload.arguments)
            result = {
                "status": "success",
                "data": raw_result,
                "metadata": {"provider": "mcp"},
            }
        else:
            result = await test_http_connector(version, payload.arguments, secret)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=type(exc).__name__,
        ) from exc
    return ToolTestResponse(**result)


@router.post("/connector-versions/{version_id}/test-connection", response_model=ToolTestResponse)
async def test_connector_connection(
    version_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> ToolTestResponse:
    user, _, _, membership = await current_user_context(request, db)
    version = await db.get(ConnectorVersion, version_id)
    connector = await db.get(Connector, version.connector_id) if version else None
    if not version or not connector or connector.workspace_id != membership.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connector Version 不存在"
        )
    if connector.owner_user_id != user.id and membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无测试权限")
    if connector.provider != "http":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="仅 HTTP Connector 支持连接测试",
        )
    spec = version.spec or {}
    # A connection test intentionally sends no user body and validates the URL,
    # authentication reference and response shape through the same gateway.
    secret = None
    if spec.get("secret_id"):
        secret = await db.scalar(
            select(SecretRecord).where(
                SecretRecord.id == spec["secret_id"],
                SecretRecord.workspace_id == membership.workspace_id,
                SecretRecord.deleted_at.is_(None),
            )
        )
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Connector Secret 不存在"
            )
    try:
        result = await test_http_connector(version, {}, secret)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=type(exc).__name__
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
            DataSource.status != "archived",
        )
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DataSource 不存在")
    if (
        source.owner_user_id != user.id
        and source.visibility != "workspace"
        and membership.role != "admin"
    ):
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


@router.post("/data-sources/{source_id}/tools/{operation:path}", response_model=ToolTestResponse)
async def invoke_data_source_tool(
    source_id: str,
    operation: str,
    payload: ToolInvocationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ToolTestResponse:
    user, _, _, membership = await current_user_context(request, db)
    source = await db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.workspace_id == membership.workspace_id,
            DataSource.status != "archived",
        )
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DataSource 不存在")
    if (
        source.owner_user_id != user.id
        and source.visibility != "workspace"
        and membership.role != "admin"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无数据源使用权限")
    secret = await db.get(SecretRecord, source.secret_id) if source.secret_id else None
    try:
        result = await invoke_database_tool(source, secret, operation, payload.arguments)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=type(exc).__name__,
        ) from exc
    return ToolTestResponse(**result)


@router.get("/connectors", response_model=list[ConnectorResponse])
async def list_connectors(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[ConnectorResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Connector).where(
            Connector.workspace_id == membership.workspace_id,
            (Connector.owner_user_id == user.id)
            | (Connector.visibility == "workspace")
            | (membership.role == "admin"),
            Connector.status == "active",
        )
    )
    responses: list[ConnectorResponse] = []
    for row in rows:
        response = _connector(row)
        draft = await db.scalar(
            select(ConnectorVersion.id)
            .where(
                ConnectorVersion.connector_id == row.id,
                ConnectorVersion.status == "draft",
            )
            .order_by(ConnectorVersion.version_number.desc())
        )
        response.draft_version_id = draft
        responses.append(response)
    return responses


@router.get("/connectors/{connector_id}/tools", response_model=list[ToolResponse])
async def list_connector_tools(
    connector_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[ToolResponse]:
    user, _, _, membership = await current_user_context(request, db)
    connector = await db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.workspace_id == membership.workspace_id,
            (Connector.owner_user_id == user.id)
            | (Connector.visibility == "workspace")
            | (membership.role == "admin"),
        )
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector 不存在")
    rows = await db.scalars(
        select(Tool).where(Tool.connector_id == connector.id).order_by(Tool.name)
    )
    return [_tool(row) for row in rows]


@router.patch("/tools/{tool_id}", response_model=ToolResponse)
async def update_tool_status(
    tool_id: str,
    payload: UpdateToolRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ToolResponse:
    user, _, _, membership = await current_user_context(request, db)
    tool = await db.scalar(
        select(Tool).where(Tool.id == tool_id, Tool.workspace_id == membership.workspace_id)
    )
    connector = await db.get(Connector, tool.connector_id) if tool else None
    if (
        not tool
        or not connector
        or not await _can_edit(connector.owner_user_id, user.id, membership.role)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool 不存在或无权限")
    tool.status = payload.status
    tool.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="tool.status_updated",
        resource_type="tool",
        resource_id=tool.id,
        metadata={"status": payload.status},
    )
    await db.commit()
    return _tool(tool)


@router.get("/connectors/{connector_id}/versions", response_model=list[ConnectorVersionResponse])
async def list_connector_versions(
    connector_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[ConnectorVersionResponse]:
    user, _, _, membership = await current_user_context(request, db)
    connector = await db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.workspace_id == membership.workspace_id,
            (Connector.owner_user_id == user.id)
            | (Connector.visibility == "workspace")
            | (membership.role == "admin"),
        )
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector 不存在")
    rows = await db.scalars(
        select(ConnectorVersion)
        .where(ConnectorVersion.connector_id == connector.id)
        .order_by(ConnectorVersion.version_number.desc())
    )
    return [_connector_version(row) for row in rows]


@router.post("/connectors/{connector_id}/versions", response_model=ConnectorVersionResponse)
async def create_connector_version(
    connector_id: str,
    payload: VersionSpecRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConnectorVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    connector = await db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.workspace_id == membership.workspace_id,
        )
    )
    if not connector or not await _can_edit(connector.owner_user_id, user.id, membership.role):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connector 不存在或无编辑权限"
        )
    latest = await db.scalar(
        select(func.max(ConnectorVersion.version_number)).where(
            ConnectorVersion.connector_id == connector.id
        )
    )
    now = utc_now()
    version = ConnectorVersion(
        id=new_id(),
        connector_id=connector.id,
        version_number=int(latest or 0) + 1,
        based_on_version_id=connector.published_version_id,
        status="draft",
        spec=_safe_spec(payload.spec),
        created_by=user.id,
        created_at=now,
    )
    db.add(version)
    for tool_spec in payload.spec.get("tools", []):
        if not isinstance(tool_spec, dict) or not tool_spec.get("name"):
            continue
        tool = await db.scalar(
            select(Tool).where(
                Tool.connector_id == connector.id,
                Tool.name == str(tool_spec["name"]),
            )
        )
        if not tool:
            tool = Tool(
                id=new_id(),
                workspace_id=membership.workspace_id,
                connector_id=connector.id,
                name=str(tool_spec["name"]),
                description=str(tool_spec.get("description", "")),
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(tool)
            await db.flush()
        latest_tool = await db.scalar(
            select(func.max(ToolVersion.version_number)).where(ToolVersion.tool_id == tool.id)
        )
        tool_version = ToolVersion(
            id=new_id(),
            tool_id=tool.id,
            connector_version_id=version.id,
            version_number=int(latest_tool or 0) + 1,
            status="draft",
            spec=dict(tool_spec),
            created_by=user.id,
            created_at=now,
        )
        db.add(tool_version)
        await db.flush()
        db.add(
            ConnectorToolBinding(
                id=new_id(),
                connector_version_id=version.id,
                tool_version_id=tool_version.id,
            )
        )
    connector.updated_at = now
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="connector.version_created",
        resource_type="connector_version",
        resource_id=version.id,
    )
    await db.commit()
    return _connector_version(version)


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    connector = await db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.workspace_id == membership.workspace_id,
            Connector.owner_user_id == user.id,
        )
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector 不存在")
    connector.status = "archived"
    connector.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="connector.archived",
        resource_type="connector",
        resource_id=connector.id,
    )
    await db.commit()


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
    bound_tool_bindings = list(
        await db.scalars(
            select(ConnectorToolBinding).where(
                ConnectorToolBinding.connector_version_id == version.id
            )
        )
    )
    for binding in bound_tool_bindings:
        tool_version = await db.get(ToolVersion, binding.tool_version_id)
        tool = await db.get(Tool, tool_version.tool_id) if tool_version else None
        if tool_version:
            tool_version.status = "published"
            tool_version.published_at = utc_now()
        if tool:
            tool.published_version_id = tool_version.id
            tool.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="connector.published",
        resource_type="connector_version",
        resource_id=version.id,
    )
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
        spec=_safe_spec(payload.spec),
        created_by=user.id,
        created_at=now,
    )
    db.add_all([plugin, version])
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.created",
        resource_type="plugin",
        resource_id=plugin.id,
    )
    await db.commit()
    response = _plugin(plugin)
    response.draft_version_id = version.id
    return response


@router.get("/plugins", response_model=list[PluginResponse])
async def list_plugins(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[PluginResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Plugin).where(
            Plugin.workspace_id == membership.workspace_id,
            (Plugin.owner_user_id == user.id)
            | (Plugin.visibility == "workspace")
            | (membership.role == "admin"),
            Plugin.status == "active",
        )
    )
    return [_plugin(row) for row in rows]


@router.get("/plugins/{plugin_id}/versions", response_model=list[PluginVersionResponse])
async def list_plugin_versions(
    plugin_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[PluginVersionResponse]:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            (Plugin.owner_user_id == user.id)
            | (Plugin.visibility == "workspace")
            | (membership.role == "admin"),
            Plugin.status == "active",
        )
    )
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    rows = await db.scalars(
        select(PluginVersion)
        .where(PluginVersion.plugin_id == plugin.id)
        .order_by(PluginVersion.version_number.desc())
    )
    return [_plugin_version(row) for row in rows]


@router.post("/plugins/{plugin_id}/versions", response_model=PluginVersionResponse)
async def create_plugin_version(
    plugin_id: str,
    payload: VersionSpecRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
        )
    )
    if not plugin or not await _can_edit(plugin.owner_user_id, user.id, membership.role):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在或无编辑权限"
        )
    latest = await db.scalar(
        select(func.max(PluginVersion.version_number)).where(PluginVersion.plugin_id == plugin.id)
    )
    now = utc_now()
    version = PluginVersion(
        id=new_id(),
        plugin_id=plugin.id,
        version_number=int(latest or 0) + 1,
        based_on_version_id=plugin.published_version_id,
        status="draft",
        spec=_safe_spec(payload.spec),
        created_by=user.id,
        created_at=now,
    )
    db.add(version)
    await db.flush()
    if plugin.published_version_id:
        skill_bindings = await db.scalars(
            select(PluginSkillBinding).where(
                PluginSkillBinding.plugin_version_id == plugin.published_version_id
            )
        )
        tool_bindings = await db.scalars(
            select(PluginToolBinding).where(
                PluginToolBinding.plugin_version_id == plugin.published_version_id
            )
        )
        resource_bindings = await db.scalars(
            select(PluginResourceBinding).where(
                PluginResourceBinding.plugin_version_id == plugin.published_version_id
            )
        )
        for binding in skill_bindings:
            db.add(
                PluginSkillBinding(
                    id=new_id(),
                    plugin_version_id=version.id,
                    skill_version_id=binding.skill_version_id,
                )
            )
        for binding in tool_bindings:
            db.add(
                PluginToolBinding(
                    id=new_id(),
                    plugin_version_id=version.id,
                    tool_version_id=binding.tool_version_id,
                )
            )
        for binding in resource_bindings:
            db.add(
                PluginResourceBinding(
                    id=new_id(),
                    plugin_version_id=version.id,
                    resource_type=binding.resource_type,
                    resource_id=binding.resource_id,
                    config=dict(binding.config or {}),
                )
            )
    plugin.updated_at = now
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.version_created",
        resource_type="plugin_version",
        resource_id=version.id,
    )
    await db.commit()
    return _plugin_version(version)


@router.patch("/plugins/{plugin_id}", response_model=PluginResponse)
async def update_plugin(
    plugin_id: str,
    payload: UpdatePluginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginResponse:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            Plugin.owner_user_id == user.id,
        )
    )
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    if payload.name is not None:
        plugin.name = payload.name.strip() or plugin.name
    if payload.description is not None:
        plugin.description = payload.description.strip()
    if payload.visibility is not None:
        plugin.visibility = payload.visibility
    if payload.spec is not None:
        latest = await db.scalar(
            select(func.max(PluginVersion.version_number)).where(
                PluginVersion.plugin_id == plugin.id
            )
        )
        db.add(
            PluginVersion(
                id=new_id(),
                plugin_id=plugin.id,
                version_number=int(latest or 0) + 1,
                based_on_version_id=plugin.published_version_id,
                status="draft",
                spec=_safe_spec(payload.spec),
                created_by=user.id,
                created_at=utc_now(),
            )
        )
    plugin.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.updated",
        resource_type="plugin",
        resource_id=plugin.id,
    )
    await db.commit()
    return _plugin(plugin)


@router.delete("/plugins/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    plugin_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            Plugin.owner_user_id == user.id,
        )
    )
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    plugin.status = "archived"
    plugin.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.archived",
        resource_type="plugin",
        resource_id=plugin.id,
    )
    await db.commit()


@router.post("/plugins/{plugin_id}/share", response_model=PluginResponse)
async def share_plugin(
    plugin_id: str,
    payload: ShareRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginResponse:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            Plugin.owner_user_id == user.id,
        )
    )
    if not plugin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin 不存在")
    if payload.visibility == "workspace" and not plugin.published_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Plugin 必须先发布才能分享"
        )
    plugin.visibility = payload.visibility
    plugin.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.shared",
        resource_type="plugin",
        resource_id=plugin.id,
        metadata={"visibility": payload.visibility},
    )
    await db.commit()
    return _plugin(plugin)


@router.post("/plugins/{plugin_id}/rollback/{version_id}", response_model=PluginVersionResponse)
async def rollback_plugin(
    plugin_id: str,
    version_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PluginVersionResponse:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            Plugin.owner_user_id == user.id,
        )
    )
    source = await db.scalar(
        select(PluginVersion).where(
            PluginVersion.id == version_id,
            PluginVersion.plugin_id == plugin_id,
            PluginVersion.status == "published",
        )
    )
    if not plugin or not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin Version 不存在")
    latest = await db.scalar(
        select(func.max(PluginVersion.version_number)).where(PluginVersion.plugin_id == plugin.id)
    )
    now = utc_now()
    draft = PluginVersion(
        id=new_id(),
        plugin_id=plugin.id,
        version_number=int(latest or 0) + 1,
        based_on_version_id=source.id,
        status="draft",
        spec=dict(source.spec or {}),
        created_by=user.id,
        created_at=now,
    )
    db.add(draft)
    await db.flush()
    for binding in await db.scalars(
        select(PluginSkillBinding).where(PluginSkillBinding.plugin_version_id == source.id)
    ):
        db.add(
            PluginSkillBinding(
                id=new_id(), plugin_version_id=draft.id, skill_version_id=binding.skill_version_id
            )
        )
    for binding in await db.scalars(
        select(PluginToolBinding).where(PluginToolBinding.plugin_version_id == source.id)
    ):
        db.add(
            PluginToolBinding(
                id=new_id(), plugin_version_id=draft.id, tool_version_id=binding.tool_version_id
            )
        )
    for binding in await db.scalars(
        select(PluginResourceBinding).where(PluginResourceBinding.plugin_version_id == source.id)
    ):
        db.add(
            PluginResourceBinding(
                id=new_id(),
                plugin_version_id=draft.id,
                resource_type=binding.resource_type,
                resource_id=binding.resource_id,
                config=dict(binding.config or {}),
            )
        )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.rollback_draft_created",
        resource_type="plugin_version",
        resource_id=draft.id,
        metadata={"based_on_version_id": source.id},
    )
    await db.commit()
    return _plugin_version(draft)


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
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.published",
        resource_type="plugin_version",
        resource_id=version.id,
    )
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
            (Plugin.owner_user_id == user.id)
            | (Plugin.visibility == "workspace")
            | (membership.role == "admin"),
            Plugin.status == "active",
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
    await db.flush()
    if source_version:
        for binding in await db.scalars(
            select(PluginSkillBinding).where(
                PluginSkillBinding.plugin_version_id == source_version.id
            )
        ):
            db.add(
                PluginSkillBinding(
                    id=new_id(),
                    plugin_version_id=clone_version.id,
                    skill_version_id=binding.skill_version_id,
                )
            )
        for binding in await db.scalars(
            select(PluginToolBinding).where(
                PluginToolBinding.plugin_version_id == source_version.id
            )
        ):
            db.add(
                PluginToolBinding(
                    id=new_id(),
                    plugin_version_id=clone_version.id,
                    tool_version_id=binding.tool_version_id,
                )
            )
        for binding in await db.scalars(
            select(PluginResourceBinding).where(
                PluginResourceBinding.plugin_version_id == source_version.id
            )
        ):
            db.add(
                PluginResourceBinding(
                    id=new_id(),
                    plugin_version_id=clone_version.id,
                    resource_type=binding.resource_type,
                    resource_id=binding.resource_id,
                    config=dict(binding.config or {}),
                )
            )
    await db.commit()
    response = _plugin(clone)
    response.draft_version_id = clone_version.id
    return response


@router.post("/plugins/{plugin_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def run_plugin(
    plugin_id: str,
    payload: PluginRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user, _, _, membership = await current_user_context(request, db)
    plugin = await db.scalar(
        select(Plugin).where(
            Plugin.id == plugin_id,
            Plugin.workspace_id == membership.workspace_id,
            Plugin.status == "active",
            (Plugin.owner_user_id == user.id)
            | (Plugin.visibility == "workspace")
            | (membership.role == "admin"),
        )
    )
    if not plugin or not plugin.published_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plugin 尚未发布")
    conversation = None
    if payload.conversation_id:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.workspace_id == membership.workspace_id,
                Conversation.owner_user_id == user.id,
                Conversation.archived_at.is_(None),
            )
        )
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    now = utc_now()
    if not conversation:
        conversation = Conversation(
            id=new_id(),
            workspace_id=membership.workspace_id,
            owner_user_id=user.id,
            title=plugin.name,
            created_at=now,
            updated_at=now,
        )
        db.add(conversation)
        await db.flush()
    run = Run(
        id=new_id(),
        workspace_id=membership.workspace_id,
        conversation_id=conversation.id,
        started_by_user_id=user.id,
        plugin_version_id=plugin.published_version_id,
        status="queued",
        idempotency_key=payload.idempotency_key,
        context_snapshot={
            "runtime_schema_version": 1,
            "plugin_version_id": plugin.published_version_id,
        },
        model_profile="reasoning",
        created_at=now,
    )
    db.add(run)
    db.add(
        Message(
            id=new_id(),
            workspace_id=membership.workspace_id,
            conversation_id=conversation.id,
            role="user",
            sequence=await next_message_sequence(db, conversation.id),
            content=payload.content,
            parts_json=[{"type": "text", "text": payload.content}],
            status="completed",
            created_at=now,
        )
    )
    conversation.updated_at = now
    await db.flush()
    await append_run_event(
        db,
        workspace_id=membership.workspace_id,
        run_id=run.id,
        event_type="run.created",
        payload={"status": "queued", "plugin_version_id": plugin.published_version_id},
    )
    await append_outbox_event(
        db,
        topic="run.created",
        payload={"run_id": run.id, "workspace_id": membership.workspace_id},
    )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="plugin.run_created",
        resource_type="plugin",
        resource_id=plugin.id,
        run_id=run.id,
    )
    await db.commit()
    return {
        "run_id": run.id,
        "conversation_id": conversation.id,
        "plugin_version_id": plugin.published_version_id,
    }


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
    skill_bindings = list(
        await db.scalars(
            select(PluginSkillBinding).where(PluginSkillBinding.plugin_version_id == version.id)
        )
    )
    tool_bindings = list(
        await db.scalars(
            select(PluginToolBinding).where(PluginToolBinding.plugin_version_id == version.id)
        )
    )
    skill_versions = [
        await db.get(SkillVersion, binding.skill_version_id) for binding in skill_bindings
    ]
    tool_versions = [
        await db.get(ToolVersion, binding.tool_version_id) for binding in tool_bindings
    ]
    invalid_refs = [
        "skill" for item in skill_versions if not item or item.status != "published"
    ] + ["tool" for item in tool_versions if not item or item.status != "published"]
    now = utc_now()
    passed = isinstance(version.spec, dict) and not invalid_refs
    result = CapabilityTestRun(
        id=new_id(),
        workspace_id=membership.workspace_id,
        resource_type="plugin",
        resource_version_id=version.id,
        status="passed" if passed else "failed",
        input_json=version.spec if isinstance(version.spec, dict) else {},
        output_json={"validated": passed, "invalid_refs": invalid_refs},
        error_summary=None if passed else "Plugin 引用的 Skill/Tool 必须先发布",
        created_by=user.id,
        created_at=now,
    )
    db.add(result)
    await db.commit()
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
    await db.execute(
        delete(PluginSkillBinding).where(PluginSkillBinding.plugin_version_id == version.id)
    )
    await db.execute(
        delete(PluginToolBinding).where(PluginToolBinding.plugin_version_id == version.id)
    )
    await db.execute(
        delete(PluginResourceBinding).where(PluginResourceBinding.plugin_version_id == version.id)
    )
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
    tools = list(
        await db.scalars(
            select(ToolVersion)
            .join(Tool)
            .where(
                ToolVersion.id.in_(payload.tool_version_ids),
                Tool.workspace_id == membership.workspace_id,
            )
        )
    )
    if len(skills) != len(set(payload.skill_version_ids)) or len(tools) != len(
        set(payload.tool_version_ids)
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
    for tool_version in tools:
        db.add(
            PluginToolBinding(
                id=new_id(),
                plugin_version_id=version.id,
                tool_version_id=tool_version.id,
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
        resource_models = {
            "knowledge_base": KnowledgeBase,
            "data_source": DataSource,
            "file": FileAsset,
            "artifact": Artifact,
            "connector_version": ConnectorVersion,
        }
        resource_model = resource_models.get(resource_type)
        if resource_model is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"不支持的 Resource 类型: {resource_type}",
            )
        resource_record = await db.get(resource_model, resource_id)
        resource_workspace_id = getattr(resource_record, "workspace_id", None)
        if isinstance(resource_record, ConnectorVersion):
            connector_record = await db.get(Connector, resource_record.connector_id)
            resource_workspace_id = connector_record.workspace_id if connector_record else None
        if not resource_record or resource_workspace_id != membership.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Resource 不存在或不属于当前 Workspace",
            )
        if hasattr(resource_record, "visibility"):
            if (
                resource_record.visibility == "private"
                and getattr(resource_record, "owner_user_id", None) != user.id
                and membership.role != "admin"
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权绑定 private Resource",
                )
        elif (
            resource_type in {"file", "artifact"}
            and getattr(resource_record, "owner_user_id", None) != user.id
            and membership.role != "admin"
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权绑定 Resource")
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
