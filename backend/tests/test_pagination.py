from datetime import date
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.pagination import PaginationParams
from app.models.item import ClothingItem, ItemStatus
from app.models.notification import Notification, NotificationStatus
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus

app = FastAPI()


@app.get("/things")
async def list_things(pagination: Annotated[PaginationParams, Depends()]) -> dict:
    return {"page": pagination.page, "page_size": pagination.page_size}


@pytest.fixture
async def things_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_defaults_to_the_first_page_of_twenty(things_client):
    response = await things_client.get("/things")
    assert response.status_code == 200
    assert response.json() == {"page": 1, "page_size": 20}


async def test_accepts_the_cap(things_client):
    response = await things_client.get("/things", params={"page": 3, "page_size": 100})
    assert response.json() == {"page": 3, "page_size": 100}


@pytest.mark.parametrize(
    "params",
    [{"page_size": 101}, {"page_size": 0}, {"page": 0}],
)
async def test_rejects_out_of_range_values(things_client, params):
    response = await things_client.get("/things", params=params)
    assert response.status_code == 422


def test_query_parameter_names_are_page_and_page_size():
    params = app.openapi()["paths"]["/things"]["get"]["parameters"]
    assert [(p["name"], p["in"]) for p in params] == [("page", "query"), ("page_size", "query")]


@pytest.mark.parametrize(
    ("page", "page_size", "total", "expected"),
    [(1, 20, 21, True), (1, 20, 20, False), (2, 20, 41, True), (3, 20, 41, False)],
)
def test_has_more(page, page_size, total, expected):
    assert PaginationParams(page=page, page_size=page_size).has_more(total) is expected


BATCH_SIZE = 13
PAGE_SIZE = 4


def _outfits(user_id, source_item: ClothingItem, source: OutfitSource) -> list[Outfit]:
    outfits = []
    for _ in range(BATCH_SIZE):
        outfit = Outfit(
            user_id=user_id,
            occasion="casual",
            scheduled_for=date.today(),
            status=OutfitStatus.pending,
            source=source,
            source_item_id=source_item.id,
        )
        outfit.items.append(OutfitItem(item_id=source_item.id, position=0))
        outfits.append(outfit)
    return outfits


def _notifications(user_id, _source_item, _source) -> list[Notification]:
    return [
        Notification(
            user_id=user_id,
            channel="ntfy",
            status=NotificationStatus.sent,
            payload={"type": "wash_reminder"},
        )
        for _ in range(BATCH_SIZE)
    ]


def _page_params(page: int) -> dict:
    return {"page": page, "page_size": PAGE_SIZE}


def _offset_params(page: int) -> dict:
    return {"offset": (page - 1) * PAGE_SIZE, "limit": PAGE_SIZE}


@pytest.mark.parametrize(
    ("url", "make_rows", "source", "params", "rows_key"),
    [
        ("/api/v1/outfits", _outfits, OutfitSource.manual, _page_params, "outfits"),
        ("/api/v1/pairings", _outfits, OutfitSource.pairing, _page_params, "pairings"),
        ("/api/v1/pairings/item/{item}", _outfits, OutfitSource.pairing, _page_params, "pairings"),
        ("/api/v1/notifications/history", _notifications, None, _offset_params, None),
    ],
    ids=["outfits", "pairings", "item-pairings", "notification-history"],
)
async def test_rows_created_together_page_in_one_total_order(
    client, db_session, test_user, auth_headers, url, make_rows, source, params, rows_key
):
    item = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.flush()
    rows = make_rows(test_user.id, item, source)
    db_session.add_all(rows)
    await db_session.commit()

    seen: list[str] = []
    for page in range(1, BATCH_SIZE // PAGE_SIZE + 2):
        response = await client.get(
            url.format(item=item.id), params=params(page), headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        seen.extend(row["id"] for row in (body[rows_key] if rows_key else body))

    # invariant: rows from one transaction share created_at, so only the id tiebreaker keeps
    # offset pages from overlapping or skipping rows.
    assert seen == sorted(str(row.id) for row in rows)
