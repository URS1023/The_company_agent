from __future__ import annotations

import re
from mimetypes import guess_type
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.core.storage import LocalFileStorage, StorageError
from backend.app.models.files import FileAsset
from backend.app.schemas.files import FileResponse
from backend.app.services.auth import current_user_context

router = APIRouter(prefix="/files", tags=["files"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".xlsm",
    ".csv",
    ".tsv",
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def _safe_name(value: str | None) -> str:
    candidate = PurePath(value or "upload.bin").name
    candidate = re.sub(r"[^\w.\- ()\u4e00-\u9fff]", "_", candidate).strip(" .")
    return candidate[:240] or "upload.bin"


def _response(file: FileAsset) -> FileResponse:
    return FileResponse.model_validate(file, from_attributes=True)


@router.post("", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    upload: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    user, _, _, membership = await current_user_context(request, db)
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件超过 100 MB",
        )
    file_id = new_id()
    name = _safe_name(upload.filename)
    suffix = PurePath(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="不支持的文件格式；支持 PDF、DOCX、XLSX、CSV、TXT、PPTX 和图片",
        )
    guessed_mime = guess_type(name)[0]
    content_type = upload.content_type or guessed_mime or "application/octet-stream"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"} and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="图片 MIME 类型不正确"
        )
    storage_key = f"workspaces/{membership.workspace_id}/files/{file_id}/{name}"
    try:
        metadata = LocalFileStorage().put_bytes(storage_key, content)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        ) from exc
    now = utc_now()
    file_asset = FileAsset(
        id=file_id,
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=name,
        mime_type=content_type,
        size=int(metadata["size"]),
        storage_key=storage_key,
        sha256=str(metadata["sha256"]),
        source_type="upload",
        status="ready",
        created_at=now,
    )
    db.add(file_asset)
    await db.commit()
    return _response(file_asset)


@router.post("/batch", response_model=list[FileResponse], status_code=status.HTTP_201_CREATED)
async def upload_files_batch(
    request: Request,
    uploads: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
) -> list[FileResponse]:
    if not uploads or len(uploads) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="单次最多上传 20 个文件"
        )
    results: list[FileResponse] = []
    for upload in uploads:
        results.append(await upload_file(request, upload, db))
    return results


@router.get("", response_model=list[FileResponse])
async def list_files(request: Request, db: AsyncSession = Depends(get_db)) -> list[FileResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(FileAsset)
        .where(
            FileAsset.workspace_id == membership.workspace_id,
            FileAsset.owner_user_id == user.id,
            FileAsset.deleted_at.is_(None),
        )
        .order_by(FileAsset.created_at.desc())
        .limit(100)
    )
    return [_response(file) for file in rows]


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    user, _, _, membership = await current_user_context(request, db)
    file_asset = await db.scalar(
        select(FileAsset).where(
            FileAsset.id == file_id,
            FileAsset.workspace_id == membership.workspace_id,
            FileAsset.owner_user_id == user.id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if not file_asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return _response(file_asset)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> None:
    user, _, _, membership = await current_user_context(request, db)
    file_asset = await db.scalar(
        select(FileAsset).where(
            FileAsset.id == file_id,
            FileAsset.workspace_id == membership.workspace_id,
            FileAsset.owner_user_id == user.id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if not file_asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    file_asset.deleted_at = utc_now()
    LocalFileStorage().delete(file_asset.storage_key)
    await db.commit()


__all__ = ["router"]
