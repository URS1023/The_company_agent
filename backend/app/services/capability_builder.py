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
