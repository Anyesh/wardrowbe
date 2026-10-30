from functools import partial
from io import BytesIO
from unittest.mock import patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw

from app.api.analytics import TypeDistribution, category_distribution
from app.services.image_service import ImageService
from app.utils.garment_vocabulary import (
    CATEGORIES,
    ROLE_CATEGORY,
    ROLES,
    TYPE_CATEGORY,
    TYPES_BY_CATEGORY,
)

JEWELRY = ("ring", "necklace", "watch", "bracelet", "earrings")


def _image_bytes(seed: int) -> bytes:
    img = Image.new("RGB", (128, 128), (15, 15, 20))
    draw = ImageDraw.Draw(img)
    for bit in range(16):
        if (seed >> bit) & 1:
            x, y = (bit % 4) * 32, (bit // 4) * 32
            draw.rectangle([x, y, x + 30, y + 30], fill=(235, 235, 240))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def storage(tmp_path):
    with patch("app.api.items.ImageService", partial(ImageService, storage_path=str(tmp_path))):
        yield tmp_path


async def _create(client: AsyncClient, headers, seed: int, **form) -> dict:
    data = {"skip_ai": "true", **form}
    resp = await client.post(
        "/api/v1/items",
        files={"image": (f"{seed}.jpg", _image_bytes(seed), "image/jpeg")},
        data=data,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_photo(client: AsyncClient, headers, item_id: str, seed: int, view=None):
    data = {"view": view} if view else {}
    return await client.post(
        f"/api/v1/items/{item_id}/images",
        files={"image": (f"{seed}.jpg", _image_bytes(seed), "image/jpeg")},
        data=data,
        headers=headers,
    )


async def _get(client: AsyncClient, headers, item_id: str) -> dict:
    resp = await client.get(f"/api/v1/items/{item_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestCategories:
    def test_every_role_is_in_exactly_one_category(self):
        assert set(ROLE_CATEGORY) == set(ROLES)
        assert set(ROLE_CATEGORY.values()) == set(CATEGORIES)

    def test_jewelry_types_are_accessories(self):
        for item_type in JEWELRY:
            assert TYPE_CATEGORY[item_type] == "accessories"
            assert item_type in TYPES_BY_CATEGORY["accessories"]
        assert TYPE_CATEGORY["shirt"] == "clothing"
        assert TYPE_CATEGORY["sneakers"] == "footwear"

    def test_category_distribution_lists_every_section(self):
        types = [
            TypeDistribution(type="shirt", count=3, percentage=0),
            TypeDistribution(type="ring", count=1, percentage=0),
        ]
        result = {c.category: (c.count, c.percentage) for c in category_distribution(types)}
        assert result == {"clothing": (3, 75.0), "footwear": (0, 0), "accessories": (1, 25.0)}

    @pytest.mark.asyncio
    async def test_items_report_and_filter_by_category(
        self, client: AsyncClient, auth_headers, storage
    ):
        ring = await _create(client, auth_headers, 1, type="ring", brand="Pandora")
        shirt = await _create(client, auth_headers, 2, type="shirt")
        assert ring["category"] == "accessories"
        assert shirt["category"] == "clothing"

        resp = await client.get("/api/v1/items?category=accessories", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert [i["id"] for i in resp.json()["items"]] == [ring["id"]]

        resp = await client.get("/api/v1/items?category=hats", headers=auth_headers)
        assert resp.status_code == 422


class TestPhotoViews:
    @pytest.mark.asyncio
    async def test_old_items_have_no_views(self, client: AsyncClient, auth_headers, storage):
        item = await _create(client, auth_headers, 3)
        assert item["image_view"] is None
        assert item["additional_images"] == []
        assert (await _get(client, auth_headers, item["id"]))["image_view"] is None

    @pytest.mark.asyncio
    async def test_front_and_back_follow_the_photo(
        self, client: AsyncClient, auth_headers, storage
    ):
        item = await _create(client, auth_headers, 4, image_view="front")
        assert item["image_view"] == "front"

        resp = await _add_photo(client, auth_headers, item["id"], 5, view="back")
        assert resp.status_code == 201, resp.text
        back = resp.json()
        assert back["view"] == "back"

        # The back becomes the cover: both labels move with their photos.
        resp = await client.post(
            f"/api/v1/items/{item['id']}/images/{back['id']}/set-primary", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        swapped = await _get(client, auth_headers, item["id"])
        assert swapped["image_view"] == "back"
        assert swapped["additional_images"][0]["view"] == "front"

    @pytest.mark.asyncio
    async def test_a_second_front_takes_the_label(self, client: AsyncClient, auth_headers, storage):
        item = await _create(client, auth_headers, 6, image_view="front")
        extra = (await _add_photo(client, auth_headers, item["id"], 7)).json()
        assert extra["view"] is None

        resp = await client.patch(
            f"/api/v1/items/{item['id']}/photo-view",
            json={"image_id": extra["id"], "view": "front"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["image_view"] is None
        assert data["additional_images"][0]["view"] == "front"

        # Details can repeat, and null clears a label.
        resp = await client.patch(
            f"/api/v1/items/{item['id']}/photo-view",
            json={"image_id": None, "view": "detail"},
            headers=auth_headers,
        )
        assert resp.json()["image_view"] == "detail"
        resp = await client.patch(
            f"/api/v1/items/{item['id']}/photo-view",
            json={"image_id": extra["id"], "view": None},
            headers=auth_headers,
        )
        assert resp.json()["additional_images"][0]["view"] is None

    @pytest.mark.asyncio
    async def test_bad_view_and_unknown_photo_are_rejected(
        self, client: AsyncClient, auth_headers, storage
    ):
        item = await _create(client, auth_headers, 8)
        resp = await client.patch(
            f"/api/v1/items/{item['id']}/photo-view",
            json={"view": "side"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        resp = await client.patch(
            f"/api/v1/items/{item['id']}/photo-view",
            json={"image_id": item["id"], "view": "back"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reorder_keeps_views(self, client: AsyncClient, auth_headers, storage):
        item = await _create(client, auth_headers, 9)
        first = (await _add_photo(client, auth_headers, item["id"], 10, view="back")).json()
        second = (await _add_photo(client, auth_headers, item["id"], 11, view="detail")).json()

        resp = await client.patch(
            f"/api/v1/items/{item['id']}/images/reorder",
            json={"image_ids": [second["id"], first["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert [(i["id"], i["view"]) for i in resp.json()] == [
            (second["id"], "detail"),
            (first["id"], "back"),
        ]


class TestPhotoLimitsAndStorage:
    @pytest.mark.asyncio
    async def test_up_to_ten_photos_counting_the_cover(
        self, client: AsyncClient, auth_headers, storage
    ):
        item = await _create(client, auth_headers, 12)
        for seed in range(13, 22):
            resp = await _add_photo(client, auth_headers, item["id"], seed)
            assert resp.status_code == 201, resp.text
        resp = await _add_photo(client, auth_headers, item["id"], 22)
        assert resp.status_code == 400
        assert "10 photos" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_deleting_a_photo_removes_its_files_and_label(
        self, client: AsyncClient, auth_headers, storage
    ):
        item = await _create(client, auth_headers, 23)
        photo = (await _add_photo(client, auth_headers, item["id"], 24, view="back")).json()
        assert (storage / photo["image_path"]).exists()

        resp = await client.delete(
            f"/api/v1/items/{item['id']}/images/{photo['id']}", headers=auth_headers
        )
        assert resp.status_code == 204
        assert not (storage / photo["image_path"]).exists()
        data = await _get(client, auth_headers, item["id"])
        assert data["additional_images"] == []
        assert data["image_view"] is None
        assert (storage / item["image_path"]).exists()

    @pytest.mark.asyncio
    async def test_deleting_an_item_removes_every_photo(
        self, client: AsyncClient, auth_headers, storage
    ):
        item = await _create(client, auth_headers, 25, image_view="front")
        photo = (await _add_photo(client, auth_headers, item["id"], 26, view="back")).json()

        resp = await client.delete(f"/api/v1/items/{item['id']}", headers=auth_headers)
        assert resp.status_code == 204
        assert not (storage / item["image_path"]).exists()
        assert not (storage / photo["image_path"]).exists()
        assert not (storage / photo["thumbnail_path"]).exists()


class TestSelectAllKeepsFilters:
    @pytest.mark.asyncio
    async def test_bulk_delete_of_a_filtered_selection_spares_the_rest(
        self, client: AsyncClient, auth_headers, storage
    ):
        await _create(client, auth_headers, 30, type="ring")
        await _create(client, auth_headers, 31, type="shirt", favorite="true")
        jeans = await _create(client, auth_headers, 32, type="jeans")

        resp = await client.post(
            "/api/v1/items/bulk/delete",
            json={"select_all": True, "filters": {"category": "accessories"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] == 1

        resp = await client.post(
            "/api/v1/items/bulk/delete",
            json={"select_all": True, "filters": {"favorite": True}},
            headers=auth_headers,
        )
        assert resp.json()["deleted"] == 1

        left = (await client.get("/api/v1/items", headers=auth_headers)).json()["items"]
        assert [i["id"] for i in left] == [jeans["id"]]


def _redis_pool():
    from unittest.mock import AsyncMock, MagicMock

    job = MagicMock()
    job.job_id = "photo-job"
    pool = AsyncMock()
    pool.enqueue_job.return_value = job
    return pool


class TestBackgroundRemovalOnEveryPhoto:
    @pytest.mark.asyncio
    async def test_each_added_photo_gets_its_own_job(
        self, client: AsyncClient, auth_headers, storage
    ):
        from unittest.mock import AsyncMock

        item = await _create(client, auth_headers, 40, image_view="front")
        pool = _redis_pool()
        with patch("app.api.items.create_pool", AsyncMock(return_value=pool)):
            first = await client.post(
                f"/api/v1/items/{item['id']}/images",
                files={"image": ("b.jpg", _image_bytes(41), "image/jpeg")},
                data={"view": "back", "remove_background": "true"},
                headers=auth_headers,
            )
            second = await client.post(
                f"/api/v1/items/{item['id']}/images",
                files={"image": ("d.jpg", _image_bytes(42), "image/jpeg")},
                data={"view": "detail", "remove_background": "true"},
                headers=auth_headers,
            )
        assert first.json()["status"] == "processing"
        assert second.json()["status"] == "processing"
        calls = [c.args for c in pool.enqueue_job.call_args_list]
        assert calls == [
            ("remove_photo_background_job", first.json()["id"], "#FFFFFF"),
            ("remove_photo_background_job", second.json()["id"], "#FFFFFF"),
        ]

    @pytest.mark.asyncio
    async def test_the_job_cleans_one_photo_and_a_failure_stays_on_it(
        self, client: AsyncClient, auth_headers, storage, db_session
    ):
        from unittest.mock import AsyncMock, MagicMock

        from PIL import Image as PILImage

        from app.models.item import ItemImage
        from app.workers.background_removal import remove_photo_background_job

        item = await _create(client, auth_headers, 43)
        good = (await _add_photo(client, auth_headers, item["id"], 44, view="back")).json()
        bad = (await _add_photo(client, auth_headers, item["id"], 45, view="detail")).json()

        ok = MagicMock()
        ok.remove.side_effect = lambda img: PILImage.new("RGBA", img.size, (0, 0, 255, 255))
        broken = MagicMock()
        broken.remove.side_effect = RuntimeError("model missing")
        worker_patches = (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", AsyncMock()),
            patch(
                "app.workers.background_removal.ImageService",
                partial(ImageService, storage_path=str(storage)),
            ),
        )
        with worker_patches[0], worker_patches[1], worker_patches[2]:
            with patch("app.services.background_removal.get_provider", return_value=ok):
                assert (await remove_photo_background_job({}, good["id"], "#FFFFFF"))[
                    "status"
                ] == "success"
            with patch("app.services.background_removal.get_provider", return_value=broken):
                assert (await remove_photo_background_job({}, bad["id"], "#FFFFFF"))[
                    "status"
                ] == "error"

        db_session.expire_all()
        cleaned = await db_session.get(ItemImage, UUID(good["id"]))
        failed = await db_session.get(ItemImage, UUID(bad["id"]))
        assert cleaned.status == "ready"
        assert cleaned.original_image_path and (storage / cleaned.original_image_path).exists()
        assert failed.status == "error"
        assert failed.original_image_path is None
        # The cover was never touched by either job.
        cover = await _get(client, auth_headers, item["id"])
        assert cover["original_image_path"] is None

        resp = await client.post(
            f"/api/v1/items/{item['id']}/images/{good['id']}/restore-original",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["original_image_path"] is None
        assert resp.json()["view"] == "back"

    @pytest.mark.asyncio
    async def test_bulk_removal_includes_the_other_photos(
        self, client: AsyncClient, auth_headers, storage
    ):
        from unittest.mock import AsyncMock

        item = await _create(client, auth_headers, 46)
        await _add_photo(client, auth_headers, item["id"], 47, view="back")
        await _add_photo(client, auth_headers, item["id"], 48, view="detail")
        pool = _redis_pool()
        with patch("app.api.items.create_pool", AsyncMock(return_value=pool)):
            resp = await client.post(
                "/api/v1/items/bulk/remove-background",
                json={"item_ids": [item["id"]]},
                headers=auth_headers,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["queued"] == 1
        assert resp.json()["photos_queued"] == 2
        names = [c.args[0] for c in pool.enqueue_job.call_args_list]
        assert names.count("remove_item_background_job") == 1
        assert names.count("remove_photo_background_job") == 2

    @pytest.mark.asyncio
    async def test_a_photo_being_processed_cannot_become_the_cover(
        self, client: AsyncClient, auth_headers, storage
    ):
        from unittest.mock import AsyncMock

        item = await _create(client, auth_headers, 49)
        pool = _redis_pool()
        with patch("app.api.items.create_pool", AsyncMock(return_value=pool)):
            photo = (
                await client.post(
                    f"/api/v1/items/{item['id']}/images",
                    files={"image": ("b.jpg", _image_bytes(50), "image/jpeg")},
                    data={"remove_background": "true"},
                    headers=auth_headers,
                )
            ).json()
        resp = await client.post(
            f"/api/v1/items/{item['id']}/images/{photo['id']}/set-primary", headers=auth_headers
        )
        assert resp.status_code == 409
