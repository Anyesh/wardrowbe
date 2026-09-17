from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.item import ClothingItem, ItemHistory, ItemStatus
from app.models.outfit import Outfit, OutfitItem


class TestApiKeyLifecycle:
    @pytest.mark.asyncio
    async def test_create_returns_plaintext_once_and_list_returns_metadata_only(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        created = await client.post(
            "/api/v1/auth/api-keys",
            headers=auth_headers,
            json={
                "name": "External bridge",
                "scopes": ["items:read", "images:read"],
            },
        )
        assert created.status_code == 201
        payload = created.json()
        assert payload["name"] == "External bridge"
        assert payload["scopes"] == ["items:read", "images:read"]
        assert payload["token"].startswith("wrb_")
        assert len(payload["token"]) >= 40
        assert payload["revoked_at"] is None
        assert payload["last_used_at"] is None

        listed = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert listed.status_code == 200
        keys = listed.json()
        assert len(keys) == 1
        assert keys[0]["id"] == payload["id"]
        assert keys[0]["name"] == "External bridge"
        assert keys[0]["scopes"] == ["items:read", "images:read"]
        assert "token" not in keys[0]
        assert "token_hash" not in keys[0]


async def _create_key(client, auth_headers, scopes, expires_at=None):
    payload = {"name": "Bridge key", "scopes": scopes}
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    response = await client.post("/api/v1/auth/api-keys", headers=auth_headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestApiKeyAuthorization:
    @pytest.mark.asyncio
    async def test_items_scope_allows_item_reads_but_denies_other_and_write_routes(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user
    ):
        key = await _create_key(client, auth_headers, ["items:read"])
        key_headers = {"Authorization": f"Bearer {key['token']}"}

        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 200
        assert (await client.get("/api/v1/users/me", headers=key_headers)).status_code == 401
        assert (
            await client.delete(f"/api/v1/items/{uuid4()}", headers=key_headers)
        ).status_code == 401
        image = await client.get(f"/api/v1/images/{test_user.id}/missing.jpg", headers=key_headers)
        assert image.status_code == 401

    @pytest.mark.asyncio
    async def test_items_write_scope_allows_generic_item_patch_only(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        write_key = await _create_key(client, auth_headers, ["items:write"])
        write_headers = {"Authorization": f"Bearer {write_key['token']}"}
        item_id = uuid4()

        allowed = await client.patch(
            f"/api/v1/items/{item_id}", json={"name": "X"}, headers=write_headers
        )
        assert allowed.status_code == 404

        read_key = await _create_key(client, auth_headers, ["items:read"])
        read_headers = {"Authorization": f"Bearer {read_key['token']}"}
        denied = await client.patch(
            f"/api/v1/items/{item_id}", json={"name": "X"}, headers=read_headers
        )
        assert denied.status_code == 401

    @pytest.mark.asyncio
    async def test_images_scope_authenticates_image_reads_only(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user
    ):
        key = await _create_key(client, auth_headers, ["images:read"])
        key_headers = {"Authorization": f"Bearer {key['token']}"}

        image = await client.get(f"/api/v1/images/{test_user.id}/missing.jpg", headers=key_headers)
        assert image.status_code == 404
        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_invalidates_key(self, client: AsyncClient, auth_headers: dict[str, str]):
        key = await _create_key(client, auth_headers, ["items:read"])
        key_headers = {"Authorization": f"Bearer {key['token']}"}
        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 200

        revoked = await client.post(
            f"/api/v1/auth/api-keys/{key['id']}/revoke", headers=auth_headers
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["revoked_at"] is not None
        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_delete_requires_inactive_key(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        key = await _create_key(client, auth_headers, ["items:read"])

        active_delete = await client.delete(
            f"/api/v1/auth/api-keys/{key['id']}", headers=auth_headers
        )
        assert active_delete.status_code == 409

        revoked = await client.post(
            f"/api/v1/auth/api-keys/{key['id']}/revoke", headers=auth_headers
        )
        assert revoked.status_code == 200

        deleted = await client.delete(f"/api/v1/auth/api-keys/{key['id']}", headers=auth_headers)
        assert deleted.status_code == 204

        listed = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert all(item["id"] != key["id"] for item in listed.json())

    @pytest.mark.asyncio
    async def test_expired_key_fails_closed(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        key = await _create_key(
            client, auth_headers, ["items:read"], datetime.now(UTC) - timedelta(minutes=1)
        )
        key_headers = {"Authorization": f"Bearer {key['token']}"}
        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_successful_use_updates_last_used_without_logging_token(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, caplog
    ):
        key = await _create_key(client, auth_headers, ["items:read"])
        key_headers = {"Authorization": f"Bearer {key['token']}"}

        assert (await client.get("/api/v1/items", headers=key_headers)).status_code == 200
        stored = await db_session.get(ApiKey, UUID(key["id"]))
        assert stored is not None
        assert stored.last_used_at is not None
        assert key["token"] not in caplog.text


@pytest.mark.asyncio
async def test_item_api_key_does_not_grant_signed_image_capability(
    client: AsyncClient, auth_headers: dict[str, str], test_user, db_session: AsyncSession
):
    item = ClothingItem(
        user_id=test_user.id,
        image_path=f"{test_user.id}/original.jpg",
        thumbnail_path=f"{test_user.id}/thumb.jpg",
        medium_path=f"{test_user.id}/medium.jpg",
        type="shirt",
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    item_key = await _create_key(client, auth_headers, ["items:read"])
    item_headers = {"Authorization": f"Bearer {item_key['token']}"}
    response = await client.get(f"/api/v1/items/{item.id}", headers=item_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["image_url"] is None
    assert payload["thumbnail_url"] is None
    assert payload["medium_url"] is None

    image_key = await _create_key(client, auth_headers, ["items:read", "images:read"])
    image_headers = {"Authorization": f"Bearer {image_key['token']}"}
    response = await client.get(f"/api/v1/items/{item.id}", headers=image_headers)

    assert response.status_code == 200
    assert "sig=" in response.json()["image_url"]

    write_key = await _create_key(client, auth_headers, ["items:write"])
    write_headers = {"Authorization": f"Bearer {write_key['token']}"}
    patched = await client.patch(
        f"/api/v1/items/{item.id}", json={"name": "No image grant"}, headers=write_headers
    )
    assert patched.status_code == 200
    assert patched.json()["image_url"] is None


@pytest.mark.asyncio
async def test_tagging_progress_does_not_grant_signed_image_capability(
    client: AsyncClient, auth_headers: dict[str, str], test_user, db_session: AsyncSession
):
    item = ClothingItem(
        user_id=test_user.id,
        image_path=f"{test_user.id}/processing.jpg",
        thumbnail_path=f"{test_user.id}/processing-thumb.jpg",
        type="shirt",
        status=ItemStatus.processing,
        ai_started_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.commit()

    item_key = await _create_key(client, auth_headers, ["items:read"])
    response = await client.get(
        "/api/v1/items/tagging-progress",
        headers={"Authorization": f"Bearer {item_key['token']}"},
    )

    assert response.status_code == 200
    current = next(row for row in response.json()["current"] if row["item_id"] == str(item.id))
    assert current["image_url"] is None

    image_key = await _create_key(client, auth_headers, ["items:read", "images:read"])
    response = await client.get(
        "/api/v1/items/tagging-progress",
        headers={"Authorization": f"Bearer {image_key['token']}"},
    )

    assert response.status_code == 200
    current = next(row for row in response.json()["current"] if row["item_id"] == str(item.id))
    assert "sig=" in current["image_url"]


@pytest.mark.asyncio
async def test_item_history_does_not_grant_signed_image_capability(
    client: AsyncClient, auth_headers: dict[str, str], test_user, db_session: AsyncSession
):
    target = ClothingItem(
        user_id=test_user.id,
        image_path=f"{test_user.id}/target.jpg",
        type="shirt",
        status=ItemStatus.ready,
    )
    companion = ClothingItem(
        user_id=test_user.id,
        image_path=f"{test_user.id}/companion.jpg",
        thumbnail_path=f"{test_user.id}/companion-thumb.jpg",
        type="pants",
        status=ItemStatus.ready,
    )
    outfit = Outfit(user_id=test_user.id, occasion="casual")
    db_session.add_all([target, companion, outfit])
    await db_session.flush()
    db_session.add(OutfitItem(outfit_id=outfit.id, item_id=companion.id, position=0))
    db_session.add(
        ItemHistory(
            item_id=target.id,
            outfit_id=outfit.id,
            worn_at=datetime.now(UTC).date(),
        )
    )
    await db_session.commit()

    item_key = await _create_key(client, auth_headers, ["items:read"])
    response = await client.get(
        f"/api/v1/items/{target.id}/history",
        headers={"Authorization": f"Bearer {item_key['token']}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["outfit"]["items"][0]["thumbnail_url"] is None

    image_key = await _create_key(client, auth_headers, ["items:read", "images:read"])
    response = await client.get(
        f"/api/v1/items/{target.id}/history",
        headers={"Authorization": f"Bearer {image_key['token']}"},
    )

    assert response.status_code == 200
    assert "sig=" in response.json()[0]["outfit"]["items"][0]["thumbnail_url"]
