import pytest

from backend.app.tools.builtin import BuiltinToolError, analyze_bidding, analyze_finance


def test_bidding_gap_detection_never_invents_missing_documents() -> None:
    result = analyze_bidding(
        project_name="智慧园区项目",
        requirements=[
            {"name": "营业执照", "search_terms": ["营业执照"]},
            {"name": "项目经理证书", "search_terms": ["项目经理证书", "项目经理资格"]},
        ],
        knowledge_text="公司营业执照扫描件和历史项目业绩",
    )
    assert result.missing == ["项目经理证书"]
    assert "[待补充：项目经理证书]" in result.document_spec["sections"][-1]["paragraphs"]
    assert "证书编号" not in str(result.document_spec)


def test_finance_summary_uses_decimal_and_creates_output_specs() -> None:
    result = analyze_finance(
        rows=[{"revenue": "100.10", "cost": "40.05"}, {"revenue": 20, "cost": 5}],
        budget=100,
    )
    assert result["summary"]["revenue"] == 120.1
    assert result["summary"]["cost"] == 45.05
    assert result["summary"]["profit"] == 75.05
    assert result["summary"]["budget_variance"] == 20.1
    assert result["presentation_spec"]["slides"]
    assert result["spreadsheet_spec"]["sheets"]["Summary"][0] == ["Metric", "Value"]


def test_builtin_tools_validate_required_inputs() -> None:
    with pytest.raises(BuiltinToolError):
        analyze_bidding(project_name="", requirements=[], knowledge_text="")
    with pytest.raises(BuiltinToolError):
        analyze_finance(rows=[])
