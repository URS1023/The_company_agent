from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from backend.app.tools.database import ReadOnlySqlError, validate_read_only_sql
from backend.app.tools.http import HttpConnectorError, HttpResult, invoke


class ToolValidationError(ValueError):
    pass


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(arguments), key=lambda error: list(error.path))
    if errors:
        raise ToolValidationError("; ".join(error.message for error in errors))


def normalize_result(result: HttpResult) -> dict[str, Any]:
    return {
        "status": "success" if 200 <= result.status_code < 300 else "failed",
        "data": result.data,
        "metadata": {"status_code": result.status_code},
    }


__all__ = [
    "HttpConnectorError",
    "ReadOnlySqlError",
    "ToolValidationError",
    "invoke",
    "normalize_result",
    "validate_arguments",
    "validate_read_only_sql",
]
