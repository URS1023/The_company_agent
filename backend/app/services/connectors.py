from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.secrets import SecretManager
from backend.app.models.capabilities import ConnectorVersion, DataSource, SecretRecord
from backend.app.tools.database import validate_read_only_sql
from backend.app.tools.gateway import normalize_result, validate_arguments
from backend.app.tools.http import invoke


class ConnectorTestError(RuntimeError):
    pass


async def test_http_connector(version: ConnectorVersion, arguments: dict) -> dict:
    spec = version.spec or {}
    schema = spec.get("input_schema") or {"type": "object"}
    validate_arguments(schema, arguments)
    result = await invoke(
        base_url=str(spec.get("base_url", "")),
        path=str(spec.get("path", "")),
        method=str(spec.get("method", "GET")),
        headers={str(k): str(v) for k, v in (spec.get("headers") or {}).items()},
        params=spec.get("query") or arguments.get("query"),
        json_body=arguments.get("body", spec.get("body")),
        allow_private=bool(spec.get("allow_private", False)),
        timeout=min(float(spec.get("timeout_seconds", 30)), 120),
    )
    return normalize_result(result)


async def test_database_connection(source: DataSource, secret: SecretRecord | None) -> dict:
    config = source.connection_config or {}
    if source.provider != "mysql":
        raise ConnectorTestError("native-dev 当前只启用 MySQL DataSource 测试")
    if not secret:
        raise ConnectorTestError("DataSource 缺少 Secret")
    values = SecretManager().decrypt(secret.nonce, secret.ciphertext)
    password = values.get("password")
    username = config.get("username") or values.get("username")
    if not password or not username:
        raise ConnectorTestError("Secret 必须包含 password，连接配置或 Secret 必须包含 username")
    host = config.get("host", "127.0.0.1")
    port = config.get("port", "3306")
    database = config.get("database", "")
    url = f"mysql+asyncmy://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}"
    engine = create_async_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return {"status": "success", "read_only": True, "provider": source.provider}
    finally:
        await engine.dispose()


def validate_database_query(sql: str, dialect: str = "mysql") -> str:
    return validate_read_only_sql(sql, dialect=dialect)


__all__ = [
    "ConnectorTestError",
    "test_database_connection",
    "test_http_connector",
    "validate_database_query",
]
