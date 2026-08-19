from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


class BuiltinToolError(ValueError):
    pass


@dataclass(slots=True)
class BidAnalysis:
    requirement_spec: dict[str, Any]
    missing: list[str]
    document_spec: dict[str, Any]


def analyze_bidding(
    *,
    project_name: str,
    requirements: list[dict[str, Any]],
    knowledge_text: str,
    template_sections: list[str] | None = None,
) -> BidAnalysis:
    if not project_name.strip():
        raise BuiltinToolError("project_name cannot be empty")
    normalized_knowledge = knowledge_text.casefold()
    missing: list[str] = []
    required_documents: list[str] = []
    for requirement in requirements:
        name = str(requirement.get("name", "")).strip()
        if not name:
            raise BuiltinToolError("each requirement needs a name")
        required_documents.append(name)
        search_terms = [
            str(term).strip()
            for term in requirement.get("search_terms", [name])
            if str(term).strip()
        ]
        if not any(term.casefold() in normalized_knowledge for term in search_terms):
            missing.append(name)
    sections = template_sections or ["项目理解", "技术方案", "实施计划", "商务响应"]
    blocks = []
    for section in sections:
        blocks.append(
            {
                "title": section,
                "paragraphs": [f"{section}：请根据已核验资料填写。"],
            }
        )
    if missing:
        blocks.append(
            {
                "title": "待补充资料",
                "paragraphs": [f"[待补充：{name}]" for name in missing],
            }
        )
    requirement_spec = {
        "project_name": project_name,
        "required_documents": required_documents,
        "required_sections": sections,
        "missing_documents": missing,
    }
    document_spec = {"title": f"{project_name} 投标文件", "sections": blocks}
    return BidAnalysis(requirement_spec, missing, document_spec)


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def analyze_finance(
    *,
    rows: list[dict[str, Any]],
    budget: Decimal | float | int = 0,
) -> dict[str, Any]:
    if not rows:
        raise BuiltinToolError("finance rows cannot be empty")
    revenue = sum(Decimal(str(row.get("revenue", 0))) for row in rows)
    cost = sum(Decimal(str(row.get("cost", 0))) for row in rows)
    profit = revenue - cost
    margin = (profit / revenue * Decimal("100")) if revenue else Decimal("0")
    budget_decimal = Decimal(str(budget))
    variance = revenue - budget_decimal
    summary = {
        "revenue": _money(revenue),
        "cost": _money(cost),
        "profit": _money(profit),
        "margin_percent": _money(margin),
        "budget": _money(budget_decimal),
        "budget_variance": _money(variance),
        "row_count": len(rows),
    }
    spreadsheet_rows = [["Metric", "Value"]] + [[key, value] for key, value in summary.items()]
    presentation = {
        "title": "财务经营分析",
        "slides": [
            {
                "title": "经营概览",
                "bullets": [
                    f"收入：{summary['revenue']:.2f}",
                    f"利润：{summary['profit']:.2f}",
                ],
            },
            {
                "title": "成本与利润率",
                "bullets": [
                    f"成本：{summary['cost']:.2f}",
                    f"利润率：{summary['margin_percent']:.2f}%",
                ],
            },
            {
                "title": "预算差异",
                "bullets": [f"预算差异：{summary['budget_variance']:.2f}"],
            },
        ],
    }
    return {
        "summary": summary,
        "spreadsheet_spec": {"sheets": {"Summary": spreadsheet_rows}},
        "presentation_spec": presentation,
    }


__all__ = ["BidAnalysis", "BuiltinToolError", "analyze_bidding", "analyze_finance"]
