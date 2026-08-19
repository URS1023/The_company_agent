from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CapabilityProposal:
    capability_type: str
    name: str
    reason: str
    spec: dict


def propose_from_user_intent(content: str) -> CapabilityProposal:
    text = content.strip()
    lowered = text.casefold()
    wants_method = "以后" in text or "方法" in text or "按这个方式" in text
    wants_connector = any(word in lowered for word in ["api", "接口", "程序", "mcp"])
    wants_plugin = any(word in text for word in ["组合", "插件", "能力包"])
    if wants_connector and not wants_plugin:
        return CapabilityProposal(
            capability_type="connector",
            name="企业接口连接器",
            reason="任务描述包含企业 API/程序接入，先生成 Connector Draft 并要求测试后发布。",
            spec={"provider": "http", "tools": [], "status": "draft"},
        )
    if wants_method and not wants_plugin:
        return CapabilityProposal(
            capability_type="skill",
            name="可复用工作方法",
            reason="用户明确要求以后复用处理方法，应保存为新的 Skill Draft。",
            spec={
                "instructions": text,
                "rules": [],
                "required_resources": [],
                "recommended_tools": [],
            },
        )
    if any(word in text for word in ["招标", "投标"]):
        return CapabilityProposal(
            capability_type="plugin",
            name="招投标文件编制",
            reason="任务包含招投标资料、规则和文档输出，适合保存方法并绑定文档 Renderer。",
            spec={
                "rules": ["企业资质禁止编造", "缺失资料必须明确标注"],
                "required_resources": ["knowledge_base", "template_file"],
                "output_types": ["document", "pdf"],
            },
        )
    if any(word in lowered for word in ["财务", "经营分析", "利润", "成本"]):
        return CapabilityProposal(
            capability_type="plugin",
            name="财务经营分析",
            reason=(
                "任务包含数据源、表格分析、图表和汇报输出，"
                "适合组合 DataSource、Analyzer 和 Renderer。"
            ),
            spec={
                "required_resources": ["data_source", "supplemental_file"],
                "tools": ["database.query", "trusted_finance_analyzer", "presentation.render"],
                "output_types": ["chart", "presentation", "spreadsheet"],
            },
        )
    return CapabilityProposal(
        capability_type="skill",
        name="可复用工作方法",
        reason="当前任务主要体现处理步骤和规则，建议先保存为 Skill Draft。",
        spec={"instructions": text, "rules": [], "required_resources": [], "recommended_tools": []},
    )


__all__ = ["CapabilityProposal", "propose_from_user_intent"]
