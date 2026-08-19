from __future__ import annotations

from pydantic import BaseModel, Field


class RenderDocumentRequest(BaseModel):
    name: str = Field(default="document.docx", min_length=1, max_length=500)
    spec: dict


class RenderPresentationRequest(BaseModel):
    name: str = Field(default="presentation.pptx", min_length=1, max_length=500)
    spec: dict


class RenderSpreadsheetRequest(BaseModel):
    name: str = Field(default="spreadsheet.xlsx", min_length=1, max_length=500)
    spec: dict
