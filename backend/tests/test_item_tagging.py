"""Tests for the item tagging lifecycle: tagging_status/tagged_by/tagged_at, the
skip_ai / vision enqueue guards, the pending work-queue filter, the PATCH
write-back origin, and the retag reset.

Covers AI-on and AI-off paths and asserts defaults preserve current behavior
(internal vision on => items are auto-tagged)."""

from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus, TaggedBy, TaggingStatus
from app.services.ai_service import ClothingTags
from app.workers.tagging import tags_to_item_fields


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 200)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeRedis:
    """Records enqueue_job calls instead of touching a real queue."""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))

        class _Job:
            job_id = "test-job"

        return _Job()

    async def aclose(self) -> None:
        pass


def _patch_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()

    async def _create_pool(*_args, **_kwargs):
        return fake

    monkeypatch.setattr("app.api.items.create_pool", _create_pool)
    return fake


# --- Schema defaults & worker origin ----------------------------------------


@pytest.mark.asyncio
async def test_new_item_defaults_to_pending(test_user, db_session: AsyncSession):
    item = ClothingItem(user_id=test_user.id, type="shirt", image_path="test/x.jpg")
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.tagging_status == TaggingStatus.pending
    assert item.tagged_by is None
    assert item.tagged_at is None


def test_auto_tag_records_auto_origin():
    fields = tags_to_item_fields(ClothingTags(type="shirt"))
    assert fields["tagging_status"] == TaggingStatus.tagged
    assert fields["tagged_by"] == TaggedBy.auto
    assert isinstance(fields["tagged_at"], datetime)


# --- create_item / bulk: skip_ai / vision enqueue guard ----------------------


@pytest.mark.asyncio
async def test_create_enqueues_when_vision_on(client: AsyncClient, auth_headers, monkeypatch):
    fake = _patch_redis(monkeypatch)
    resp = await client.post(
        "/api/v1/items",
        headers=auth_headers,
        files={"image": ("x.png", _png_bytes(), "image/png")},
        data={"type": "shirt"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    assert body["tagging_status"] == "pending"
    assert len(fake.jobs) == 1


@pytest.mark.asyncio
async def test_create_with_skip_ai_leaves_pending(client: AsyncClient, auth_headers, monkeypatch):
    fake = _patch_redis(monkeypatch)
    resp = await client.post(
        "/api/v1/items",
        headers=auth_headers,
        files={"image": ("x.png", _png_bytes(), "image/png")},
        data={"type": "shirt", "skip_ai": "true"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["tagging_status"] == "pending"
    assert fake.jobs == []


@pytest.mark.asyncio
async def test_create_leaves_pending_when_vision_disabled(
    client: AsyncClient, auth_headers, monkeypatch
):
    fake = _patch_redis(monkeypatch)
    monkeypatch.setattr("app.api.items.settings", Settings(ai_internal_enabled=False))
    resp = await client.post(
        "/api/v1/items",
        headers=auth_headers,
        files={"image": ("x.png", _png_bytes(), "image/png")},
        data={"type": "shirt"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["tagging_status"] == "pending"
    assert fake.jobs == []


@pytest.mark.asyncio
async def test_bulk_create_with_skip_ai_leaves_pending(
    client: AsyncClient, auth_headers, monkeypatch
):
    fake = _patch_redis(monkeypatch)
    resp = await client.post(
        "/api/v1/items/bulk",
        headers=auth_headers,
        files=[("images", ("x.png", _png_bytes(), "image/png"))],
        data={"skip_ai": "true"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["results"][0]["item"]
    assert body["status"] == "ready"
    assert body["tagging_status"] == "pending"
    assert body["tagged_by"] is None
    assert fake.jobs == []


# --- Pending work-queue filter ----------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_tagging_status_pending(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    pending = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        image_path="test/p.jpg",
        status=ItemStatus.ready,
        tagging_status=TaggingStatus.pending,
    )
    tagged = ClothingItem(
        user_id=test_user.id,
        type="pants",
        image_path="test/t.jpg",
        status=ItemStatus.ready,
        tagging_status=TaggingStatus.tagged,
        tagged_by=TaggedBy.auto,
    )
    db_session.add_all([pending, tagged])
    await db_session.commit()

    resp = await client.get(
        "/api/v1/items", params={"tagging_status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["type"] == "shirt"
    assert data["items"][0]["tagging_status"] == "pending"


# --- PATCH write-back marks a pending item tagged with a server-derived origin ---


async def _make_pending_item(test_user, db_session, type_="unknown") -> ClothingItem:
    item = ClothingItem(
        user_id=test_user.id,
        type=type_,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        tagging_status=TaggingStatus.pending,
    )
    db_session.add(item)
    await db_session.commit()
    return item


@pytest.mark.asyncio
async def test_patch_writeback_marks_tagged_by_manual(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_pending_item(test_user, db_session)
    resp = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"type": "shirt", "primary_color": "blue"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tagging_status"] == "tagged"
    assert body["tagged_by"] == "manual"
    assert body["tagged_at"] is not None


@pytest.mark.asyncio
async def test_patch_non_tag_field_does_not_mark_tagged(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_pending_item(test_user, db_session, type_="shirt")
    resp = await client.patch(
        f"/api/v1/items/{item.id}", json={"favorite": True}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["favorite"] is True
    assert body["tagging_status"] == "pending"
    assert body["tagged_by"] is None


@pytest.mark.asyncio
async def test_patch_with_empty_tag_values_does_not_mark_tagged(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_pending_item(test_user, db_session, type_="shirt")
    resp = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"colors": [], "primary_color": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tagging_status"] == "pending"
    assert body["tagged_by"] is None
    assert body["tagged_at"] is None


@pytest.mark.asyncio
async def test_patch_does_not_rewrite_existing_origin(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        image_path="test/tagged.jpg",
        status=ItemStatus.ready,
        tagging_status=TaggingStatus.tagged,
        tagged_by=TaggedBy.auto,
        tagged_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/items/{item.id}", json={"type": "jacket"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "jacket"
    assert body["tagging_status"] == "tagged"
    assert body["tagged_by"] == "auto"  # origin preserved, not rewritten to manual


@pytest.mark.asyncio
async def test_tagged_by_cannot_be_forged_via_body(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_pending_item(test_user, db_session)
    resp = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"type": "shirt", "tagged_by": "auto", "tagging_status": "tagged"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    # Origin is server-derived (manual = supplied via the API), ignoring the body fields.
    assert resp.json()["tagged_by"] == "manual"


# --- retag resets to the pending queue --------------------------------------


@pytest.mark.asyncio
async def test_retag_resets_to_pending(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        image_path="test/r.jpg",
        status=ItemStatus.ready,
        tagging_status=TaggingStatus.tagged,
        tagged_by=TaggedBy.auto,
        tagged_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client.post(f"/api/v1/items/{item.id}/retag", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tagging_status"] == "pending"
    assert body["tagged_by"] is None
    assert body["tagged_at"] is None


@pytest.mark.asyncio
async def test_retag_unknown_item_404(client: AsyncClient, auth_headers):
    resp = await client.post(f"/api/v1/items/{uuid4()}/retag", headers=auth_headers)
    assert resp.status_code == 404


# --- Tag write-back projects onto first-class columns (not just the JSONB) ----


@pytest.mark.asyncio
async def test_patch_tags_projects_to_columns(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_pending_item(test_user, db_session)
    resp = await client.patch(
        f"/api/v1/items/{item.id}",
        json={
            "tags": {
                "pattern": "solid",
                "material": "linen",
                "style": ["casual"],
                "season": ["summer"],
                "formality": "casual",
                "colors": ["blue", "white"],
                "primary_color": "blue",
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Columns projected from the tags block.
    assert body["pattern"] == "solid"
    assert body["material"] == "linen"
    assert body["style"] == ["casual"]
    assert body["season"] == ["summer"]
    assert body["formality"] == "casual"
    assert body["colors"] == ["blue", "white"]
    assert body["primary_color"] == "blue"
    # JSONB carries them too, and it counts as a tag write-back.
    assert body["tags"]["pattern"] == "solid"
    assert body["tagging_status"] == "tagged"
