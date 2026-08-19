from __future__ import annotations

import re

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


__all__ = ["ReadOnlySqlError", "validate_read_only_sql"]
