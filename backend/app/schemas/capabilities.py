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


class PluginResponse(BaseModel):
    id: str
    name: str
    description: str
    visibility: str
    published_version_id: str | None
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


class DataSourceResponse(BaseModel):
    id: str
    name: str
    provider: str
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
    connector_version_ids: list[str] = Field(default_factory=list)
    resources: list[dict[str, str]] = Field(default_factory=list)


__all__ = [
    "ConnectorResponse",
    "ConnectorVersionResponse",
    "CreateConnectorRequest",
    "CreateDataSourceRequest",
    "CreatePluginRequest",
    "CreateSecretRequest",
    "CreateSkillRequest",
    "DataSourceResponse",
    "PluginResponse",
    "PluginVersionResponse",
    "SecretResponse",
    "SkillResponse",
    "SkillVersionResponse",
    "ToolInvocationRequest",
    "ToolTestResponse",
    "VersionSpecRequest",
    "CapabilityTestRunResponse",
    "PluginBindingRequest",
]
