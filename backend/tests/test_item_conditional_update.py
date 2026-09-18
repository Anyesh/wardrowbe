import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus


async def _api_key_headers(client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=auth_headers,
        json={"name": "External item writer", "scopes": ["items:read", "items:write"]},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def _item(db_session: AsyncSession, test_user) -> ClothingItem:
    item = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        name="Original",
        image_path="test/conditional.jpg",
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_item_response_exposes_opaque_revision(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _item(db_session, test_user)
    headers = await _api_key_headers(client, auth_headers)

    response = await client.get(f"/api/v1/items/{item.id}", headers=headers)

    assert response.status_code == 200, response.text
    revision = response.json()["revision"]
    assert revision.startswith("v1-")
    assert "T" not in revision


@pytest.mark.asyncio
async def test_conditional_patch_rejects_stale_revision_without_overwrite(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _item(db_session, test_user)
    headers = await _api_key_headers(client, auth_headers)
    initial = await client.get(f"/api/v1/items/{item.id}", headers=headers)
    revision = initial.json()["revision"]

    first = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"name": "First writer"},
        headers={**headers, "If-Match": f'"{revision}"'},
    )
    assert first.status_code == 200, first.text
    assert first.json()["name"] == "First writer"
    assert first.json()["revision"] != revision

    stale = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"name": "Stale writer"},
        headers={**headers, "If-Match": f'"{revision}"'},
    )
    assert stale.status_code == 412, stale.text

    current = await client.get(f"/api/v1/items/{item.id}", headers=headers)
    assert current.status_code == 200
    assert current.json()["name"] == "First writer"


@pytest.mark.asyncio
async def test_conditional_patch_rejects_wildcard_embedded_in_quoted_tag(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _item(db_session, test_user)
    headers = await _api_key_headers(client, auth_headers)

    response = await client.patch(
        f"/api/v1/items/{item.id}",
        json={"name": "Should not update"},
        headers={**headers, "If-Match": '"other,*,tag"'},
    )

    assert response.status_code == 412, response.text
    current = await client.get(f"/api/v1/items/{item.id}", headers=headers)
    assert current.json()["name"] == "Original"
