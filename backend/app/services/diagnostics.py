from __future__ import annotations


def classify_failure(error_code: str | None, error_summary: str | None) -> dict[str, str]:
    code = (error_code or "RUNTIME_ERROR").upper()
    text = (error_summary or "").lower()
    if code in {"TOOLVALIDATIONERROR", "TOOL_ARGUMENT_VALIDATION_FAILED"} or "schema" in text:
        return {
            "category": "parameter_error",
            "owner": "parameter_compiler",
            "next_action": "修改参数映射或补充缺失输入后重试",
        }
    if code in {"HTTPCONNECTORERROR", "PROVIDERRESPONSEERROR"} or "connector" in text:
        return {
            "category": "connector_adapter_error",
            "owner": "connector",
            "next_action": "检查接口地址、认证引用和 Connector Draft，不修改外部程序",
        }
    if code in {"READONLYSQLERROR", "CONNECTORTESTERROR"} or "database" in text:
        return {
            "category": "data_error",
            "owner": "data_source",
            "next_action": "检查只读数据源、表名和查询条件",
        }
    if code in {"EXTERNAL_CHAT_DISABLED", "MODEL_NOT_CONFIGURED"}:
        return {
            "category": "configuration_error",
            "owner": "model_profile",
            "next_action": "配置并安全 Probe 对应模型 Profile",
        }
    if code in {"HTTPException", "PERMISSION_DENIED"} or "permission" in text or "权限" in text:
        return {
            "category": "permission_error",
            "owner": "workspace_policy",
            "next_action": "请管理员授予资源使用权限",
        }
    return {
        "category": "runtime_error",
        "owner": "runtime",
        "next_action": "查看步骤和 Tool Trace，确认输入后再重试",
    }


__all__ = ["classify_failure"]
