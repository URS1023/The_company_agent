from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.services.auth import current_user_context
from backend.app.tools.builtin import analyze_bidding, analyze_finance

router = APIRouter(prefix="/demos", tags=["demos"])


class BiddingDemoRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=500)
    requirements: list[dict] = Field(default_factory=list, max_length=200)
    knowledge_text: str = Field(default="", max_length=200_000)
    template_sections: list[str] | None = Field(default=None, max_length=100)


class FinanceDemoRequest(BaseModel):
    rows: list[dict] = Field(min_length=1, max_length=100_000)
    budget: float = 0


@router.post("/bidding/analyze")
async def bidding_demo(
    payload: BiddingDemoRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    await current_user_context(request, db)
    result = analyze_bidding(
        project_name=payload.project_name,
        requirements=payload.requirements,
        knowledge_text=payload.knowledge_text,
        template_sections=payload.template_sections,
    )
    return {
        "demo": "bidding",
        "requirement_spec": result.requirement_spec,
        "missing": result.missing,
        "document_spec": result.document_spec,
    }


@router.post("/finance/analyze")
async def finance_demo(
    payload: FinanceDemoRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    await current_user_context(request, db)
    return {"demo": "finance", **analyze_finance(rows=payload.rows, budget=payload.budget)}


__all__ = ["router"]
