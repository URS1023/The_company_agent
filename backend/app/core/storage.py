from __future__ import annotations

import hashlib
import os
from pathlib import Path

from backend.app.core.config import settings


class StorageError(RuntimeError):
    pass


class LocalFileStorage:
    """Safe native-dev storage adapter; S3/MinIO can implement the same interface later."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.local_storage_root).resolve()

    def _path(self, storage_key: str) -> Path:
        if not storage_key or storage_key.startswith(("/", "\\")):
            raise StorageError("invalid storage key")
        candidate = (self.root / storage_key).resolve()
        if os.path.commonpath([str(self.root), str(candidate)]) != str(self.root):
            raise StorageError("storage path escaped root")
        return candidate

    def put_bytes(self, storage_key: str, content: bytes) -> dict[str, object]:
        if len(content) > settings.local_storage_max_bytes:
            raise StorageError("storage quota exceeded")
        target = self._path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(content)
        temp.replace(target)
        return {
            "storage_key": storage_key,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def get_bytes(self, storage_key: str) -> bytes:
        target = self._path(storage_key)
        if not target.is_file():
            raise StorageError("storage object not found")
        return target.read_bytes()

    def delete(self, storage_key: str) -> None:
        target = self._path(storage_key)
        if target.exists():
            target.unlink()


__all__ = ["LocalFileStorage", "StorageError"]
