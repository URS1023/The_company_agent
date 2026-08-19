from __future__ import annotations


def _login(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert response.status_code == 200


def test_bidding_demo_returns_gap_and_document_spec(client, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/demos/bidding/analyze",
        json={
            "project_name": "智慧园区项目",
            "requirements": [
                {"name": "营业执照", "search_terms": ["营业执照"]},
                {"name": "项目经理证书", "search_terms": ["项目经理证书"]},
            ],
            "knowledge_text": "公司营业执照和历史业绩",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] == "bidding"
    assert body["missing"] == ["项目经理证书"]
    assert "[待补充：项目经理证书]" in body["document_spec"]["sections"][-1]["paragraphs"]


def test_finance_demo_returns_decimal_summary_and_output_specs(client, admin_seed) -> None:
    _login(client)
    response = client.post(
        "/api/v1/demos/finance/analyze",
        json={
            "rows": [{"revenue": "100.10", "cost": "40.05"}, {"revenue": 20, "cost": 5}],
            "budget": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] == "finance"
    assert body["summary"]["profit"] == 75.05
    assert body["presentation_spec"]["slides"]
    assert body["spreadsheet_spec"]["sheets"]["Summary"]
