from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DocumentProcessingError(RuntimeError):
    pass


@dataclass(slots=True)
class ParsedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    locations: list[dict[str, Any]] = field(default_factory=list)


def _parse_text(data: bytes, name: str) -> ParsedDocument:
    return ParsedDocument(
        text=data.decode("utf-8", errors="replace"),
        metadata={"format": Path(name).suffix.lower().lstrip(".") or "txt"},
    )


def _parse_csv(data: bytes, name: str) -> ParsedDocument:
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    normalized = "\n".join("\t".join(cell.strip() for cell in row) for row in rows)
    return ParsedDocument(
        text=normalized,
        metadata={"format": "csv", "rows": len(rows), "columns": len(rows[0]) if rows else 0},
    )


def _parse_json(data: bytes) -> ParsedDocument:
    try:
        value = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DocumentProcessingError("JSON 文件格式不正确") from exc
    return ParsedDocument(
        text=json.dumps(value, ensure_ascii=False, indent=2), metadata={"format": "json"}
    )


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DocumentProcessingError("未安装 PyMuPDF") from exc
    pages: list[str] = []
    locations: list[dict[str, Any]] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        for index, page in enumerate(document):
            page_text = page.get_text("text").strip()
            pages.append(page_text)
            locations.append({"page": index + 1})
    return ParsedDocument(
        text="\n\n".join(pages),
        metadata={"format": "pdf", "pages": len(pages)},
        locations=locations,
    )


def _parse_docx(data: bytes) -> ParsedDocument:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DocumentProcessingError("未安装 python-docx") from exc
    document = Document(io.BytesIO(data))
    paragraphs = [
        paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
    ]
    tables: list[str] = []
    for table in document.tables:
        tables.append(
            "\n".join("\t".join(cell.text.strip() for cell in row.cells) for row in table.rows)
        )
    text = "\n".join(paragraphs + tables)
    return ParsedDocument(text=text, metadata={"format": "docx", "tables": len(tables)})


def _parse_xlsx(data: bytes) -> ParsedDocument:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DocumentProcessingError("未安装 openpyxl") from exc
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sections: list[str] = []
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            values = ["" if value is None else str(value) for value in row]
            if any(values):
                rows.append("\t".join(values))
        sections.append(f"[Sheet: {sheet.title}]\n" + "\n".join(rows))
    return ParsedDocument(
        text="\n\n".join(sections),
        metadata={"format": "xlsx", "sheets": workbook.sheetnames},
    )


def _parse_pptx(data: bytes) -> ParsedDocument:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DocumentProcessingError("未安装 python-pptx") from exc
    presentation = Presentation(io.BytesIO(data))
    slides: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts = [
            shape.text.strip()
            for shape in slide.shapes
            if hasattr(shape, "text") and shape.text.strip()
        ]
        slides.append(f"[Slide: {index}]\n" + "\n".join(texts))
    return ParsedDocument(
        text="\n\n".join(slides),
        metadata={"format": "pptx", "slides": len(presentation.slides)},
    )


def parse_document(data: bytes, name: str, mime_type: str | None = None) -> ParsedDocument:
    suffix = Path(name).suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return _parse_csv(data, name)
    if suffix == ".json" or mime_type == "application/json":
        return _parse_json(data)
    if suffix in {".txt", ".md", ".markdown", ".html", ".xml"} or (mime_type or "").startswith(
        "text/"
    ):
        return _parse_text(data, name)
    if suffix == ".pdf" or mime_type == "application/pdf":
        return _parse_pdf(data)
    if suffix == ".docx":
        return _parse_docx(data)
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_xlsx(data)
    if suffix == ".pptx":
        return _parse_pptx(data)
    if (mime_type or "").startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        raise DocumentProcessingError("图片需要通过 Vision/OCR Profile 解析")
    raise DocumentProcessingError(f"暂不支持文件格式：{suffix or mime_type or 'unknown'}")


def chunk_text(text: str, target_chars: int = 3600, overlap_chars: int = 400) -> list[str]:
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + target_chars)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


__all__ = ["DocumentProcessingError", "ParsedDocument", "chunk_text", "parse_document"]
