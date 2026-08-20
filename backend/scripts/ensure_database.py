from __future__ import annotations

import argparse
import asyncio
import re
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.config import settings


def validate_database_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError("database name must contain only ASCII letters, digits and underscores")
    return name


async def ensure_database(database_name: str | None = None) -> str:
    target = validate_database_name(database_name or make_url(settings.mysql_url).database or "")
    parsed = make_url(settings.mysql_url)
    server_url = parsed.set(database=None)
    engine = create_async_engine(
        server_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
    )
    try:
        async with engine.begin() as connection:
            existing = await connection.scalar(
                text(
                    "SELECT SCHEMA_NAME FROM information_schema.schemata "
                    "WHERE SCHEMA_NAME = :database_name"
                ),
                {"database_name": target},
            )
            if existing:
                return target
            await connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{target}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                )
            )
    finally:
        await engine.dispose()
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the configured Company Agent MySQL database exists."
    )
    parser.add_argument("--database", default=None)
    args = parser.parse_args()
    try:
        database = asyncio.run(ensure_database(args.database))
    except Exception as exc:  # pragma: no cover - local environment specific
        print(f"database.ensure=failed:{type(exc).__name__}")
        return 1
    print(f"database.ensure=ready:{database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
