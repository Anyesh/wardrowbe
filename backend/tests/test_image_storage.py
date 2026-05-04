from pathlib import Path

import pytest

from app.services.image_storage import LocalImageStorage


@pytest.mark.asyncio
async def test_local_storage_put_get_delete(tmp_path: Path):
    storage = LocalImageStorage(tmp_path)

    await storage.put_bytes("user/a.jpg", b"image-bytes", "image/jpeg")

    assert await storage.get_bytes("user/a.jpg") == b"image-bytes"
    assert (tmp_path / "user" / "a.jpg").exists()

    await storage.delete("user/a.jpg")

    assert not (tmp_path / "user" / "a.jpg").exists()


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path):
    storage = LocalImageStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put_bytes("../escape.jpg", b"x", "image/jpeg")
