from functools import partial
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw

from app.services.image_service import ImageService


def _image_bytes(i: int) -> bytes:
    img = Image.new("RGB", (128, 128), (15, 15, 20))
    d = ImageDraw.Draw(img)
    for bit in range(16):
        if (i >> bit) & 1:
            cx, cy = (bit % 4) * 32, (bit // 4) * 32
            d.rectangle([cx, cy, cx + 30, cy + 30], fill=(235, 235, 240))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _redis_pool():
    job = AsyncMock()
    job.job_id = str(uuid4())
    pool = AsyncMock()
    pool.enqueue_job.return_value = job
    return pool


def _enqueued_paths(pool) -> list[str]:
    return [c.args[2] for c in pool.enqueue_job.call_args_list if c.args[0] == "tag_item_image"]


class TestEnqueuedImagePathUsesStorageRoot:
    @pytest.mark.asyncio
    async def test_single_upload_and_reanalyze(self, client: AsyncClient, auth_headers, tmp_path):
        pool = _redis_pool()
        with (
            patch("app.api.items.ImageService", partial(ImageService, storage_path=str(tmp_path))),
            patch("app.api.items.create_pool", new_callable=AsyncMock, return_value=pool),
        ):
            resp = await client.post(
                "/api/v1/items",
                files={"image": ("a.jpg", _image_bytes(1), "image/jpeg")},
                headers=auth_headers,
            )
            assert resp.status_code == 201
            item = resp.json()
            expected = str(tmp_path / item["image_path"])
            assert _enqueued_paths(pool) == [expected]

            pool.enqueue_job.reset_mock()
            await client.post(f"/api/v1/items/{item['id']}/cancel-analysis", headers=auth_headers)
            resp = await client.post(f"/api/v1/items/{item['id']}/analyze", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "queued"

        assert _enqueued_paths(pool) == [expected]
        assert (tmp_path / item["image_path"]).exists()

    @pytest.mark.asyncio
    async def test_bulk_upload(self, client: AsyncClient, auth_headers, tmp_path):
        pool = _redis_pool()
        files = [("images", (f"i{i}.jpg", _image_bytes(i + 2), "image/jpeg")) for i in range(2)]
        with (
            patch("app.api.items.ImageService", partial(ImageService, storage_path=str(tmp_path))),
            patch("app.api.items.create_pool", new_callable=AsyncMock, return_value=pool),
        ):
            resp = await client.post("/api/v1/items/bulk", files=files, headers=auth_headers)

        assert resp.status_code == 201
        paths = _enqueued_paths(pool)
        assert len(paths) == 2
        for path in paths:
            assert path.startswith(f"{tmp_path}/")
