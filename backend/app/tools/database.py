from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


class ReadOnlySqlError(ValueError):
    pass


_FORBIDDEN_TOKENS = {
    "insert",
    "update",
    "delete",
    "merge",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "outfile",
    "load_file",
    "sleep",
    "benchmark",
}


def validate_read_only_sql(sql: str, dialect: str = "mysql") -> str:
    normalized = sql.strip()
    if not normalized:
        raise ReadOnlySqlError("SQL cannot be empty")
    if ";" in normalized.rstrip(";"):
        raise ReadOnlySqlError("multiple SQL statements are not allowed")
    lowered = normalized.lower()
    if any(re.search(rf"\b{re.escape(token)}\b", lowered) for token in _FORBIDDEN_TOKENS):
        raise ReadOnlySqlError("statement contains a forbidden operation")
    if "for update" in lowered or "lock in share mode" in lowered:
        raise ReadOnlySqlError("locking reads are not allowed")
    try:
        tree = parse_one(normalized, read=dialect)
    except ParseError as exc:
        raise ReadOnlySqlError("SQL could not be parsed") from exc
    if isinstance(
        tree,
        (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Merge,
            exp.Create,
            exp.Drop,
            exp.Alter,
            exp.TruncateTable,
        ),
    ):
        raise ReadOnlySqlError("only read-only SELECT statements are allowed")
    if not isinstance(tree, (exp.Select, exp.Union, exp.With)):
        raise ReadOnlySqlError("only read-only SELECT statements are allowed")
    return tree.sql(dialect=dialect)


def _quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value):
        raise ReadOnlySqlError("identifier contains unsafe characters")
    return value


def create_database_engine(source: Any, values: dict[str, str]) -> AsyncEngine:
    provider = str(source.provider)
    config = source.connection_config or {}
    username = config.get("username") or values.get("username")
    password = values.get("password", "")
    host = config.get("host", "127.0.0.1")
    port = config.get("port", "3306" if provider == "mysql" else "5432")
    database = config.get("database", "")
    if not username or not database:
        raise ReadOnlySqlError("DataSource 必须提供 username 和 database")
    from urllib.parse import quote_plus

    scheme = "mysql+asyncmy" if provider == "mysql" else "postgresql+asyncpg"
    return create_async_engine(
        f"{scheme}://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


async def database_list_tables(engine: AsyncEngine, provider: str) -> dict[str, Any]:
    if provider == "mysql":
        query = text(
            "SELECT TABLE_NAME AS table_name, TABLE_TYPE AS table_type "
            "FROM information_schema.tables "
            "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
        )
    else:
        query = text(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
    async with engine.connect() as connection:
        result = await connection.execute(query)
        return {"status": "success", "data": [dict(row._mapping) for row in result]}


async def database_describe_table(
    engine: AsyncEngine, provider: str, table_name: str
) -> dict[str, Any]:
    safe_table = _quote_identifier(table_name)
    if provider == "mysql":
        query = text(
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, "
            "IS_NULLABLE AS is_nullable, COLUMN_KEY AS column_key "
            "FROM information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table_name ORDER BY ORDINAL_POSITION"
        )
    else:
        query = text(
            "SELECT column_name, data_type, is_nullable, '' AS column_key "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = :table_name ORDER BY ordinal_position"
        )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"table_name": safe_table})
        return {
            "status": "success",
            "data": {"table_name": safe_table, "columns": [dict(row._mapping) for row in result]},
        }


async def database_query(
    engine: AsyncEngine, provider: str, sql: str, *, max_rows: int = 1000
) -> dict[str, Any]:
    normalized = validate_read_only_sql(sql, dialect="mysql" if provider == "mysql" else "postgres")
    async with engine.connect() as connection:
        result = await connection.execute(text(normalized))
        rows = [dict(row._mapping) for row in result.fetchmany(max_rows)]
        return {"status": "success", "data": rows, "metadata": {"row_count": len(rows)}}


__all__ = [
    "ReadOnlySqlError",
    "create_database_engine",
    "database_describe_table",
    "database_list_tables",
    "database_query",
    "validate_read_only_sql",
]
