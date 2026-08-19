from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any


class RendererError(RuntimeError):
    pass


@dataclass(slots=True)
class DocumentSpec:
    title: str
    sections: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PresentationSpec:
    title: str
    slides: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SpreadsheetSpec:
    sheets: dict[str, list[list[Any]]] = field(default_factory=dict)


def render_docx(spec: DocumentSpec) -> bytes:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise RendererError("未安装 python-docx") from exc
    document = Document()
    document.add_heading(spec.title, level=0)
    for section in spec.sections:
        title = str(section.get("title", ""))
        if title:
            document.add_heading(title, level=1)
        for paragraph in section.get("paragraphs", []):
            document.add_paragraph(str(paragraph))
        for table in section.get("tables", []):
            rows = list(table)
            if not rows:
                continue
            word_table = document.add_table(rows=len(rows), cols=len(rows[0]))
            for row_index, row in enumerate(rows):
                for col_index, value in enumerate(row):
                    word_table.cell(row_index, col_index).text = str(value)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def render_pptx(spec: PresentationSpec) -> bytes:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover
        raise RendererError("未安装 python-pptx") from exc
    presentation = Presentation()
    title_layout = presentation.slide_layouts[0]
    title_slide = presentation.slides.add_slide(title_layout)
    title_slide.shapes.title.text = spec.title
    for slide_spec in spec.slides:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = str(slide_spec.get("title", ""))
        body = slide.placeholders[1].text_frame
        body.clear()
        bullets = slide_spec.get("bullets", []) or [slide_spec.get("body", "")]
        for index, bullet in enumerate(bullets):
            paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
            paragraph.text = str(bullet)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def render_xlsx(spec: SpreadsheetSpec) -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RendererError("未安装 openpyxl") from exc
    workbook = Workbook()
    first = True
    for name, rows in spec.sheets.items():
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = name[:31] or "Sheet1"
        for row in rows:
            sheet.append([str(value) if value is not None else "" for value in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


__all__ = [
    "DocumentSpec",
    "PresentationSpec",
    "RendererError",
    "SpreadsheetSpec",
    "render_docx",
    "render_pptx",
    "render_xlsx",
]
