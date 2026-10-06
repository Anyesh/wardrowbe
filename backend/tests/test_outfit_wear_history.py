from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.item import ClothingItem, ItemStatus


async def _items(db_session, user_id):
    items = [
        ClothingItem(
            id=uuid4(),
            user_id=user_id,
            type=item_type,
            image_path=f"test/{item_type}.jpg",
            status=ItemStatus.ready,
            primary_color="blue",
        )
        for item_type in ("t-shirt", "jeans", "sneakers")
    ]
    db_session.add_all(items)
    await db_session.commit()
    return [str(item.id) for item in items]


async def _history(client, auth_headers, item_id):
    response = await client.get(f"/api/v1/items/{item_id}/history", headers=auth_headers)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_a_studio_outfit_marked_worn_appears_in_each_items_wear_history(
    client: AsyncClient, db_session, test_user, auth_headers
):
    item_ids = await _items(db_session, test_user.id)

    created = await client.post(
        "/api/v1/outfits/studio",
        json={
            "items": item_ids,
            "occasion": "casual",
            "scheduled_for": "2026-10-01",
            "mark_worn": True,
        },
        headers=auth_headers,
    )

    assert created.status_code == 201
    outfit_id = created.json()["id"]
    for item_id in item_ids:
        [entry] = await _history(client, auth_headers, item_id)
        assert entry["worn_at"] == "2026-10-01"
        assert entry["occasion"] == "casual"
        assert entry["outfit"]["id"] == outfit_id


@pytest.mark.asyncio
async def test_worn_feedback_records_one_history_entry_per_item_even_when_sent_twice(
    client: AsyncClient, db_session, test_user, auth_headers
):
    item_ids = await _items(db_session, test_user.id)
    created = await client.post(
        "/api/v1/outfits/studio",
        json={"items": item_ids, "occasion": "work", "scheduled_for": "2026-10-02"},
        headers=auth_headers,
    )
    outfit_id = created.json()["id"]

    for _ in range(2):
        response = await client.post(
            f"/api/v1/outfits/{outfit_id}/feedback", json={"worn": True}, headers=auth_headers
        )
        assert response.status_code == 200

    for item_id in item_ids:
        [entry] = await _history(client, auth_headers, item_id)
        assert entry["outfit"]["id"] == outfit_id
        assert entry["occasion"] == "work"
    item = await client.get(f"/api/v1/items/{item_ids[0]}", headers=auth_headers)
    assert item.json()["wear_count"] == 1
