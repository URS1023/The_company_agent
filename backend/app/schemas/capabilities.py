from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateSecretRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=64)
    value: dict[str, str] = Field(min_length=1)


class SecretResponse(BaseModel):
    id: str
    name: str
    provider: str
    status: str
    created_at: datetime
    updated_at: datetime


class CreateSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: str = Field(default="private", pattern="^(private|workspace)$")
    spec: dict = Field(default_factory=dict)


class UpdateSkillRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: str | None = Field(default=None, pattern="^(private|workspace)$")
    spec: dict | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    visibility: str
    published_version_id: str | None
    created_at: datetime
    updated_at: datetime


class SkillVersionResponse(BaseModel):
    id: str
    skill_id: str
    version_number: int
    status: str
    spec: dict
    created_at: datetime
    published_at: datetime | None


class CreateConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(pattern="^(http|mcp|database|builtin|sandbox)$")
    visibility: str = Field(default="private", pattern="^(private|workspace)$")
    spec: dict = Field(default_factory=dict)


class ConnectorBuilderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    provider: str = Field(default="http", pattern="^(http|mcp|database|builtin|sandbox)$")
    base_url: str = ""
    path: str = ""
    method: str = Field(default="POST", pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class ConnectorBuilderResponse(BaseModel):
    spec: dict
    warnings: list[str] = Field(default_factory=list)


class ConnectorResponse(BaseModel):
    id: str
    name: str
    provider: str
    visibility: str
    published_version_id: str | None
    created_at: datetime
    updated_at: datetime


class ConnectorVersionResponse(BaseModel):
    id: str
    connector_id: str
    version_number: int
    status: str
    spec: dict
    created_at: datetime
    published_at: datetime | None


class CreatePluginRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: str = Field(default="private", pattern="^(private|workspace)$")
    spec: dict = Field(default_factory=dict)


class UpdatePluginRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: str | None = Field(default=None, pattern="^(private|workspace)$")
    spec: dict | None = None


class PluginResponse(BaseModel):
    id: str
    name: str
    description: str
    visibility: str
    published_version_id: str | None
    draft_version_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PluginVersionResponse(BaseModel):
    id: str
    plugin_id: str
    version_number: int
    status: str
    spec: dict
    created_at: datetime
    published_at: datetime | None


class CreateDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(pattern="^(mysql|postgresql)$")
    connection_config: dict[str, str] = Field(default_factory=dict)
    secret_id: str | None = None
    visibility: str = Field(default="workspace", pattern="^(private|workspace)$")


class UpdateDataSourceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    connection_config: dict[str, str] | None = None
    secret_id: str | None = None
    visibility: str | None = Field(default=None, pattern="^(private|workspace)$")


class DataSourceResponse(BaseModel):
    id: str
    name: str
    provider: str
    visibility: str
    connection_config: dict[str, str]
    secret_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ToolInvocationRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


class ToolTestResponse(BaseModel):
    status: str
    data: dict | list | str | None = None
    metadata: dict = Field(default_factory=dict)


class ToolResponse(BaseModel):
    id: str
    connector_id: str
    name: str
    description: str
    status: str
    published_version_id: str | None


class UpdateToolRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class VersionSpecRequest(BaseModel):
    spec: dict = Field(default_factory=dict)


class CapabilityTestRunResponse(BaseModel):
    id: str
    resource_type: str
    resource_version_id: str
    status: str
    output_json: dict
    error_summary: str | None
    created_at: datetime


class PluginBindingRequest(BaseModel):
    skill_version_ids: list[str] = Field(default_factory=list)
    tool_version_ids: list[str] = Field(default_factory=list)
    resources: list[dict[str, str]] = Field(default_factory=list)


class ShareRequest(BaseModel):
    visibility: str = Field(pattern="^(private|workspace)$")


class PluginRunRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class CapabilityProposalResponse(BaseModel):
    capability_type: str
    name: str
    reason: str
    spec: dict


class CapabilityDraftRequest(BaseModel):
    capability_type: str = Field(pattern="^(skill|plugin)$")


class CapabilityDraftResponse(BaseModel):
    capability_type: str
    resource_id: str
    version_id: str
    status: str = "draft"


__all__ = [
    "ConnectorResponse",
    "ConnectorVersionResponse",
    "CreateConnectorRequest",
    "ConnectorBuilderRequest",
    "ConnectorBuilderResponse",
    "CreateDataSourceRequest",
    "UpdateDataSourceRequest",
    "CreatePluginRequest",
    "UpdatePluginRequest",
    "CreateSecretRequest",
    "CreateSkillRequest",
    "UpdateSkillRequest",
    "DataSourceResponse",
    "PluginResponse",
    "PluginVersionResponse",
    "SecretResponse",
    "SkillResponse",
    "SkillVersionResponse",
    "ToolInvocationRequest",
    "ToolResponse",
    "ToolTestResponse",
    "UpdateToolRequest",
    "VersionSpecRequest",
    "CapabilityTestRunResponse",
    "PluginBindingRequest",
    "PluginRunRequest",
    "ShareRequest",
    "CapabilityProposalResponse",
    "CapabilityDraftRequest",
    "CapabilityDraftResponse",
]
