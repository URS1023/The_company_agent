from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FileResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    sha256: str
    status: str
    source_type: str
    created_at: datetime


__all__ = ["FileResponse"]
