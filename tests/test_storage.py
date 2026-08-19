import pytest

from backend.app.core.storage import LocalFileStorage, StorageError


def test_local_storage_round_trip_and_hash(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    metadata = storage.put_bytes("workspace-a/input.txt", b"hello")
    assert metadata["size"] == 5
    assert len(metadata["sha256"]) == 64
    assert storage.get_bytes("workspace-a/input.txt") == b"hello"


def test_local_storage_rejects_path_escape(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.put_bytes("../outside.txt", b"secret")


def test_local_storage_rejects_absolute_key(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.put_bytes("C:\\outside.txt", b"secret")
