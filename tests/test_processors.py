from __future__ import annotations

import io

import fitz
import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from backend.app.processors.documents import DocumentProcessingError, parse_document
from backend.app.processors.renderers import (
    DocumentSpec,
    PresentationSpec,
    SpreadsheetSpec,
    render_docx,
    render_pdf,
    render_pptx,
    render_xlsx,
)


def test_parse_text_csv_and_json() -> None:
    assert "hello" in parse_document(b"hello", "note.txt", "text/plain").text
    assert "header\tvalue" in parse_document(b"header,value\n1,2", "data.csv", "text/csv").text
    assert (
        '"name": "demo"' in parse_document(b'{"name":"demo"}', "data.json", "application/json").text
    )


def test_parse_pdf_docx_xlsx_and_pptx() -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PDF requirement")
    assert "PDF requirement" in parse_document(pdf.tobytes(), "brief.pdf", "application/pdf").text

    doc = Document()
    doc.add_paragraph("DOCX requirement")
    doc_buffer = io.BytesIO()
    doc.save(doc_buffer)
    assert "DOCX requirement" in parse_document(doc_buffer.getvalue(), "brief.docx").text

    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active.append(["Revenue", 100])
    xlsx_buffer = io.BytesIO()
    workbook.save(xlsx_buffer)
    assert "Revenue" in parse_document(xlsx_buffer.getvalue(), "data.xlsx").text

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "PPT requirement"
    pptx_buffer = io.BytesIO()
    presentation.save(pptx_buffer)
    assert "PPT requirement" in parse_document(pptx_buffer.getvalue(), "brief.pptx").text


def test_renderers_produce_openable_office_files() -> None:
    docx_bytes = render_docx(
        DocumentSpec(
            title="Bid",
            sections=[{"title": "Scope", "paragraphs": ["Do not invent facts"]}],
        )
    )
    doc = Document(io.BytesIO(docx_bytes))
    assert "Bid" in "\n".join(paragraph.text for paragraph in doc.paragraphs)

    pptx_bytes = render_pptx(
        PresentationSpec(title="Finance", slides=[{"title": "Summary", "bullets": ["Revenue"]}])
    )
    presentation = Presentation(io.BytesIO(pptx_bytes))
    assert len(presentation.slides) == 2

    xlsx_bytes = render_xlsx(SpreadsheetSpec(sheets={"Summary": [["Revenue", 100]]}))
    workbook = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    assert workbook["Summary"]["A1"].value == "Revenue"
    pdf_bytes = render_pdf(DocumentSpec(title="PDF", sections=[{"paragraphs": ["Summary"]}]))
    assert "Summary" in parse_document(pdf_bytes, "result.pdf", "application/pdf").text


def test_images_require_vision_or_ocr() -> None:
    with pytest.raises(DocumentProcessingError, match="Vision/OCR"):
        parse_document(b"not-an-image", "scan.png", "image/png")
