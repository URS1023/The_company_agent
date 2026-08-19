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


def validate_source_policy(arguments: dict[str, Any], policy: dict[str, Any] | None = None) -> None:
    """Enforce declared field provenance before a Tool call.

    A model may provide `__sources: {field: "database|knowledge|llm"}` as
    metadata.  The metadata is removed by the caller before external dispatch;
    it is never sent to the business program.
    """

    if not policy:
        return
    sources = arguments.get("__sources") or {}
    for field, rule in policy.items():
        if not isinstance(rule, dict):
            continue
        declared = sources.get(field)
        expected = rule.get("source")
        if rule.get("allow_llm_generate") is False and expected and declared != expected:
            raise ToolValidationError(f"{field} 必须来自 {expected}")
        if rule.get("require_citation") and not arguments.get("__citations"):
            raise ToolValidationError(f"{field} 缺少来源引用")


def normalize_result(result: HttpResult) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if isinstance(result.data, dict) and result.data.get("url"):
        artifacts.append(
            {
                "type": result.data.get("type", "external"),
                "name": result.data.get("name", "external-result"),
                "mime_type": result.data.get("mime_type"),
                "url": result.data["url"],
            }
        )
    return {
        "status": "success" if 200 <= result.status_code < 300 else "failed",
        "data": result.data,
        "artifacts": artifacts,
        "metadata": {"status_code": result.status_code},
    }


__all__ = [
    "HttpConnectorError",
    "ReadOnlySqlError",
    "ToolValidationError",
    "invoke",
    "normalize_result",
    "validate_arguments",
    "validate_source_policy",
    "validate_read_only_sql",
]
