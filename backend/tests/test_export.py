import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.preference import UserPreference
from app.models.user import User

URL = "/api/v1/items/export"


def _item(user: User, type_: str, **fields) -> ClothingItem:
    return ClothingItem(
        user_id=user.id,
        type=type_,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **fields,
    )


async def _add(db: AsyncSession, *items: ClothingItem) -> list[ClothingItem]:
    db.add_all(items)
    await db.commit()
    for item in items:
        await db.refresh(item)
    return list(items)


async def _other_user(db: AsyncSession) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        external_id=f"export-{uid}",
        email=f"export-{uid}@example.com",
        display_name="Someone Else",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_skill_groups_items_by_role_and_numbers_them(
    client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
):
    await _add(
        db_session,
        _item(test_user, "sneakers", name="White runners", primary_color="white"),
        _item(
            test_user,
            "shirt",
            subtype="oxford",
            primary_color="light-blue",
            colors=["light-blue", "white"],
            ai_description="Crisp oxford shirt with a button-down collar.",
        ),
        _item(test_user, "jeans", primary_color="navy", tags={"fit": "slim"}),
    )

    response = await client.post(URL, json={"format": "skill"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert 'filename="SKILL.md"' in response.headers["content-disposition"]
    body = response.text
    assert body.startswith("---\nname: wardrobe-stylist\ndescription: ")
    assert "3 items" in body
    # Sections follow the order a person dresses, and numbering runs across them.
    tops, bottoms, footwear = (
        body.index("### Tops (1)"),
        body.index("### Bottoms (1)"),
        body.index("### Footwear (1)"),
    )
    assert tops < bottoms < footwear
    assert "[1] oxford (shirt)" in body
    assert "color: light-blue (with white)" in body
    assert "Crisp oxford shirt" in body
    assert "fit: slim" in body
    assert '[3] "White runners" - sneakers' in body


@pytest.mark.asyncio
async def test_never_exports_another_users_items(
    client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
):
    other = await _other_user(db_session)
    [mine, theirs] = await _add(
        db_session,
        _item(test_user, "shirt", name="Mine"),
        _item(other, "shirt", name="Theirs"),
    )

    by_filter = await client.post(URL, json={"format": "text"}, headers=auth_headers)
    by_id = await client.post(
        URL,
        json={"format": "text", "item_ids": [str(mine.id), str(theirs.id)]},
        headers=auth_headers,
    )

    for response in (by_filter, by_id):
        assert response.status_code == 200
        assert "Mine" in response.text
        assert "Theirs" not in response.text


@pytest.mark.asyncio
async def test_follows_filters_and_exclusions_like_select_all(
    client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
):
    kept, excluded, _, _ = await _add(
        db_session,
        _item(test_user, "shirt", name="Kept shirt"),
        _item(test_user, "shirt", name="Excluded shirt"),
        _item(test_user, "pants", name="Filtered pants"),
        _item(test_user, "shirt", name="Archived shirt", is_archived=True),
    )

    response = await client.post(
        URL,
        json={
            "format": "text",
            "filters": {"type": "shirt"},
            "excluded_ids": [str(excluded.id)],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "Kept shirt" in response.text
    for missing in ("Excluded shirt", "Filtered pants", "Archived shirt"):
        assert missing not in response.text


@pytest.mark.asyncio
async def test_profile_is_included_only_when_asked(
    client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
):
    test_user.body_measurements = {"shoe_size": "43", "waist": ""}
    db_session.add(UserPreference(user_id=test_user.id, color_favorites=["olive"]))
    await _add(db_session, _item(test_user, "shirt"))

    with_profile = await client.post(URL, json={"format": "skill"}, headers=auth_headers)
    without_profile = await client.post(
        URL, json={"format": "skill", "include_profile": False}, headers=auth_headers
    )
    as_json = await client.post(
        URL, json={"format": "json", "include_profile": False}, headers=auth_headers
    )

    assert "Favorite colors: olive" in with_profile.text
    assert "shoe size: 43" in with_profile.text
    assert "waist" not in with_profile.text
    assert "olive" not in without_profile.text
    assert "shoe size" not in without_profile.text
    assert "profile" not in json.loads(as_json.text)


@pytest.mark.asyncio
async def test_json_lists_every_item_without_account_details(
    client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
):
    [shirt] = await _add(db_session, _item(test_user, "shirt", name="Linen shirt"))

    response = await client.post(URL, json={"format": "json"}, headers=auth_headers)

    assert response.status_code == 200
    payload = json.loads(response.text)
    assert payload["item_count"] == 1
    assert payload["items"][0]["id"] == str(shirt.id)
    assert payload["items"][0]["name"] == "Linen shirt"
    assert test_user.email not in response.text


@pytest.mark.asyncio
async def test_rejects_unknown_formats(client: AsyncClient, test_user: User, auth_headers):
    response = await client.post(URL, json={"format": "pdf"}, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_requires_authentication(client: AsyncClient):
    response = await client.post(URL, json={"format": "skill"})
    assert response.status_code == 401
