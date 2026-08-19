from __future__ import annotations

import httpx

from backend.app.core.secrets import SecretManager
from backend.app.models.capabilities import ConnectorVersion, DataSource, SecretRecord
from backend.app.tools.database import (
    create_database_engine,
    database_describe_table,
    database_list_tables,
    database_query,
    validate_read_only_sql,
)
from backend.app.tools.gateway import normalize_result, validate_arguments
from backend.app.tools.http import invoke, validate_target


class ConnectorTestError(RuntimeError):
    pass


async def test_http_connector(
    version: ConnectorVersion, arguments: dict, secret: SecretRecord | None = None
) -> dict:
    spec = version.spec or {}
    schema = spec.get("input_schema") or {"type": "object"}
    validate_arguments(schema, arguments)
    headers = {str(k): str(v) for k, v in (spec.get("headers") or {}).items()}
    if secret:
        secret_values = SecretManager().decrypt(secret.nonce, secret.ciphertext)
        auth_type = str(spec.get("auth_type", "bearer")).lower()
        if auth_type == "api_key" and secret_values.get("api_key"):
            headers[str(spec.get("api_key_header", "X-API-Key"))] = secret_values["api_key"]
        elif (
            auth_type == "basic" and secret_values.get("username") and secret_values.get("password")
        ):
            import base64

            token = base64.b64encode(
                f"{secret_values['username']}:{secret_values['password']}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {token}"
        elif secret_values.get("token"):
            headers["Authorization"] = f"Bearer {secret_values['token']}"
        elif auth_type in {"oauth2", "oauth2_client_credentials"}:
            token_url = validate_target(
                str(spec.get("token_url", "")),
                allow_private=bool(spec.get("allow_private", False)),
            )
            token_response = await _oauth_client_credentials_token(
                token_url,
                client_id=str(secret_values.get("client_id", "")),
                client_secret=str(secret_values.get("client_secret", "")),
                scope=str(spec.get("scope", "")),
            )
            headers["Authorization"] = f"Bearer {token_response}"
    result = await invoke(
        base_url=str(spec.get("base_url", "")),
        path=str(spec.get("path", "")),
        method=str(spec.get("method", "GET")),
        headers=headers,
        params=spec.get("query") or arguments.get("query"),
        json_body=arguments.get("body", spec.get("body")),
        allow_private=bool(spec.get("allow_private", False)),
        timeout=min(float(spec.get("timeout_seconds", 30)), 120),
    )
    return normalize_result(result)


async def _oauth_client_credentials_token(
    token_url: str, *, client_id: str, client_secret: str, scope: str = ""
) -> str:
    if not client_id or not client_secret:
        raise ConnectorTestError("OAuth2 Secret 必须包含 client_id 和 client_secret")
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.post(token_url, data=data)
    if response.is_error:
        raise ConnectorTestError(f"OAuth2 token endpoint returned HTTP {response.status_code}")
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise ConnectorTestError("OAuth2 token response 缺少 access_token")
    return token


async def test_database_connection(source: DataSource, secret: SecretRecord | None) -> dict:
    config = source.connection_config or {}
    if source.provider not in {"mysql", "postgresql"}:
        raise ConnectorTestError(f"不支持的 DataSource Provider: {source.provider}")
    if not secret:
        raise ConnectorTestError("DataSource 缺少 Secret")
    values = SecretManager().decrypt(secret.nonce, secret.ciphertext)
    password = values.get("password")
    username = config.get("username") or values.get("username")
    if not password or not username:
        raise ConnectorTestError("Secret 必须包含 password，连接配置或 Secret 必须包含 username")
    engine = create_database_engine(source, {"username": username, "password": password})
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return {"status": "success", "read_only": True, "provider": source.provider}
    finally:
        await engine.dispose()


def validate_database_query(sql: str, dialect: str = "mysql") -> str:
    return validate_read_only_sql(sql, dialect=dialect)


async def invoke_database_tool(
    source: DataSource,
    secret: SecretRecord | None,
    operation: str,
    arguments: dict,
) -> dict:
    if not secret:
        raise ConnectorTestError("DataSource 缺少 Secret")
    values = SecretManager().decrypt(secret.nonce, secret.ciphertext)
    config = source.connection_config or {}
    if not values.get("password"):
        raise ConnectorTestError("Secret 必须包含 password")
    engine = create_database_engine(
        source,
        {
            "username": config.get("username") or values.get("username", ""),
            "password": values["password"],
        },
    )
    try:
        if operation == "database.list_tables":
            return await database_list_tables(engine, source.provider)
        if operation == "database.describe_table":
            return await database_describe_table(
                engine, source.provider, str(arguments["table_name"])
            )
        if operation == "database.query":
            return await database_query(
                engine,
                source.provider,
                str(arguments["sql"]),
                max_rows=min(int(arguments.get("max_rows", 1000)), 1000),
            )
        if operation == "database.describe":
            return {
                "status": "success",
                "data": {
                    "provider": source.provider,
                    "database": config.get("database", ""),
                    "read_only": True,
                },
            }
        raise ConnectorTestError(f"不支持的 Database operation: {operation}")
    finally:
        await engine.dispose()


__all__ = [
    "ConnectorTestError",
    "test_database_connection",
    "test_http_connector",
    "invoke_database_tool",
    "validate_database_query",
]
