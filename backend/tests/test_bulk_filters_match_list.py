from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.outfits import BulkOutfitFilters
from app.main import app
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitSource, OutfitStatus
from app.schemas.item import BulkFilters

ITEMS = {
    "needs-wash": {"needs_wash": True},
    "favorite": {"favorite": True},
    "plain": {},
    "archived-needs-wash": {"needs_wash": True, "is_archived": True},
}


async def _seed_items(db_session: AsyncSession, user_id) -> dict[str, str]:
    items = {
        key: ClothingItem(
            user_id=user_id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
            **overrides,
        )
        for key, overrides in ITEMS.items()
    }
    db_session.add_all(items.values())
    await db_session.commit()
    return {str(item.id): key for key, item in items.items()}


@pytest.fixture
def fake_redis():
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
        redis = AsyncMock()
        redis.enqueue_job.return_value.job_id = "job-id"
        mock_create_pool.return_value = redis
        yield redis


@pytest.mark.parametrize("entry_point", ["list", "bulk-delete", "bulk-rotate"])
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"needs_wash": True, "is_archived": False}, {"needs-wash"}),
        ({"favorite": True, "is_archived": False}, {"favorite"}),
    ],
)
async def test_item_select_all_acts_on_the_rows_the_list_shows(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    auth_headers,
    fake_redis,
    entry_point,
    filters,
    expected,
):
    user_id = test_user.id
    keys_by_id = await _seed_items(db_session, user_id)

    if entry_point == "list":
        response = await client.get("/api/v1/items", params=filters, headers=auth_headers)
        assert response.status_code == 200
        matched = {item["id"] for item in response.json()["items"]}
    elif entry_point == "bulk-delete":
        response = await client.post(
            "/api/v1/items/bulk/delete",
            json={"select_all": True, "filters": filters},
            headers=auth_headers,
        )
        assert response.status_code == 200
        db_session.expire_all()
        remaining = await db_session.scalars(
            select(ClothingItem.id).where(ClothingItem.user_id == user_id)
        )
        matched = set(keys_by_id) - {str(item_id) for item_id in remaining}
    else:
        response = await client.post(
            "/api/v1/items/bulk/rotate",
            json={"select_all": True, "direction": "cw", "filters": filters},
            headers=auth_headers,
        )
        assert response.status_code == 200
        db_session.expire_all()
        processing = await db_session.scalars(
            select(ClothingItem.id).where(
                ClothingItem.user_id == user_id, ClothingItem.status == ItemStatus.processing
            )
        )
        matched = {str(item_id) for item_id in processing}

    assert {keys_by_id[item_id] for item_id in matched} == expected


@pytest.mark.parametrize("entry_point", ["list", "bulk-delete"])
@pytest.mark.parametrize("status_value", ["accepted", "accepted, "])
async def test_outfit_select_all_applies_the_status_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    auth_headers,
    entry_point,
    status_value,
):
    user_id = test_user.id
    outfits = {
        key: Outfit(
            user_id=user_id,
            occasion="casual",
            scheduled_for=date.today(),
            status=outfit_status,
            source=OutfitSource.manual,
        )
        for key, outfit_status in {
            "accepted": OutfitStatus.accepted,
            "pending": OutfitStatus.pending,
            "rejected": OutfitStatus.rejected,
        }.items()
    }
    db_session.add_all(outfits.values())
    await db_session.commit()
    keys_by_id = {str(outfit.id): key for key, outfit in outfits.items()}
    filters = {"status": status_value}

    if entry_point == "list":
        response = await client.get("/api/v1/outfits", params=filters, headers=auth_headers)
        assert response.status_code == 200
        matched = {outfit["id"] for outfit in response.json()["outfits"]}
    else:
        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"select_all": True, "filters": filters},
            headers=auth_headers,
        )
        assert response.status_code == 200
        db_session.expire_all()
        remaining = await db_session.scalars(select(Outfit.id).where(Outfit.user_id == user_id))
        matched = set(keys_by_id) - {str(outfit_id) for outfit_id in remaining}

    assert {keys_by_id[outfit_id] for outfit_id in matched} == {"accepted"}


UNKNOWN_KEY_BODIES = [
    {"select_all": True, "filters": {"bogus": 1}},
    {"select_all": True, "filter": {}},
]


@pytest.mark.parametrize(
    "body",
    [
        *UNKNOWN_KEY_BODIES,
        {"select_all": True, "filters": {"needswash": True}},
        {"select_all": True, "filters": {"is_archived": None}},
        {"select_all": True, "filters": {"status": "bogus"}},
        {"select_all": True, "filters": {"tagging_status": "bogus"}},
    ],
)
async def test_item_bulk_refuses_unknown_keys_and_deletes_nothing(
    client: AsyncClient, db_session: AsyncSession, test_user, auth_headers, body
):
    await _seed_items(db_session, test_user.id)

    response = await client.post("/api/v1/items/bulk/delete", json=body, headers=auth_headers)

    assert response.status_code == 422
    count = await db_session.scalar(
        select(func.count()).select_from(ClothingItem).where(ClothingItem.user_id == test_user.id)
    )
    assert count == len(ITEMS)


@pytest.mark.parametrize(
    "body",
    [
        *UNKNOWN_KEY_BODIES,
        {"select_all": True, "filters": {"status_filter": "accepted"}},
        {"select_all": True, "filters": {"status": "bogus"}},
        {"select_all": True, "filters": {"status": "accepted,bogus"}},
        {"select_all": True, "filters": {"source": "bogus"}},
    ],
)
async def test_outfit_bulk_refuses_unknown_keys_and_deletes_nothing(
    client: AsyncClient, db_session: AsyncSession, test_user, auth_headers, body
):
    db_session.add(
        Outfit(
            user_id=test_user.id,
            occasion="casual",
            scheduled_for=date.today(),
            status=OutfitStatus.pending,
            source=OutfitSource.manual,
        )
    )
    await db_session.commit()

    response = await client.post("/api/v1/outfits/bulk/delete", json=body, headers=auth_headers)

    assert response.status_code == 422
    count = await db_session.scalar(
        select(func.count()).select_from(Outfit).where(Outfit.user_id == test_user.id)
    )
    assert count == 1


# Names only: colors and occasions are comma strings in the query and lists in the bulk body.
@pytest.mark.parametrize(
    ("list_path", "bulk_filters", "list_only"),
    [
        ("/api/v1/items", BulkFilters, {"page", "page_size", "sort_by", "sort_order"}),
        (
            "/api/v1/outfits",
            BulkOutfitFilters,
            {"page", "page_size", "family_member_id", "source_type"},
        ),
    ],
)
def test_bulk_filters_name_every_list_filter(list_path, bulk_filters, list_only):
    parameters = app.openapi()["paths"][list_path]["get"]["parameters"]
    query_names = {p["name"] for p in parameters if p["in"] == "query"}

    assert query_names - list_only == set(bulk_filters.model_fields)
