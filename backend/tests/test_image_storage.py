from pathlib import Path

import pytest

from app.services import image_storage
from app.services.image_storage import LocalImageStorage


@pytest.mark.asyncio
async def test_local_storage_put_get_delete(tmp_path: Path):
    storage = LocalImageStorage(tmp_path)

    await storage.put_bytes("user/a.jpg", b"image-bytes", "image/jpeg")

    assert await storage.get_bytes("user/a.jpg") == b"image-bytes"
    assert (tmp_path / "user" / "a.jpg").exists()

    await storage.delete("user/a.jpg")

    assert not (tmp_path / "user" / "a.jpg").exists()


@pytest.mark.parametrize(
    "key",
    [
        "../escape.jpg",
        "/tmp/escape.jpg",
        "user/../../escape.jpg",
    ],
)
@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path, key: str):
    storage = LocalImageStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put_bytes(key, b"x", "image/jpeg")


@pytest.mark.asyncio
async def test_local_storage_runs_disk_operations_in_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    storage = LocalImageStorage(tmp_path)
    calls: list[str] = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(image_storage.asyncio, "to_thread", fake_to_thread)

    await storage.put_bytes("user/a.jpg", b"image-bytes", "image/jpeg")
    assert await storage.get_bytes("user/a.jpg") == b"image-bytes"
    await storage.delete("user/a.jpg")

    assert calls == ["_write_file", "read_bytes", "_delete_file"]
