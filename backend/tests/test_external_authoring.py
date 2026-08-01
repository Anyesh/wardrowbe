"""External outfit authoring: the agent-facing write surface for suggestions
and pairings (POST /outfits/suggestions, POST /pairings/item/{item_id}).

Covers persistence as Outfit(source=external), ownership enforcement, the
authoring attributes (season/formality/palette/notes), pairing list/delete
inclusion, and availability with internal AI off.
"""

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus
from app.models.user import User


def _make_item(user_id, item_type="shirt", **kwargs) -> ClothingItem:
    return ClothingItem(
        user_id=user_id,
        type=item_type,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **kwargs,
    )


async def _make_wardrobe(
    db_session: AsyncSession, user: User, types: list[str]
) -> list[ClothingItem]:
    items = [_make_item(user.id, item_type=t) for t in types]
    db_session.add_all(items)
    await db_session.commit()
    return items


async def _make_foreign_item(db_session: AsyncSession) -> ClothingItem:
    unique_id = str(uuid4())[:8]
    other = User(
        id=uuid4(),
        external_id=f"other-user-{unique_id}",
        email=f"other-{unique_id}@example.com",
        display_name="Other User",
        timezone="UTC",
        is_active=True,
        onboarding_completed=False,
    )
    db_session.add(other)
    await db_session.flush()
    item = _make_item(other.id)
    db_session.add(item)
    await db_session.commit()
    return item


# --- POST /outfits/suggestions ----------------------------------------------


@pytest.mark.asyncio
async def test_create_suggestion_persists_external_outfit(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans, sneakers = await _make_wardrobe(
        db_session, test_user, ["shirt", "jeans", "sneakers"]
    )

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={
            "items": [str(sneakers.id), str(shirt.id), str(jeans.id)],
            "occasion": "casual",
            "name": "Weekend look",
            "reasoning": "Light layers for a mild day",
            "style_notes": "Roll the sleeves",
            "season": "Summer",
            "formality": "casual",
            "palette": ["Navy", " white "],
            "notes": "Pairs well with the canvas tote",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "external"
    assert body["status"] == "pending"
    assert body["occasion"] == "casual"
    assert body["name"] == "Weekend look"
    assert body["reasoning"] == "Light layers for a mild day"
    assert body["style_notes"] == "Roll the sleeves"
    assert body["season"] == "summer"
    assert body["formality"] == "casual"
    assert body["palette"] == ["navy", "white"]
    assert body["notes"] == "Pairs well with the canvas tote"
    assert body["scheduled_for"] is not None
    # Positions follow the request order
    assert [i["id"] for i in body["items"]] == [str(sneakers.id), str(shirt.id), str(jeans.id)]


@pytest.mark.asyncio
async def test_create_suggestion_defaults_attributes_to_null(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id), str(jeans.id)], "occasion": "office", "palette": []},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["season"] is None
    assert body["formality"] is None
    # palette=[] collapses to null
    assert body["palette"] is None
    assert body["notes"] is None
    assert body["name"] is None


@pytest.mark.asyncio
async def test_create_suggestion_accepts_explicit_scheduled_for(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={
            "items": [str(shirt.id), str(jeans.id)],
            "occasion": "casual",
            "scheduled_for": "2026-08-01",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scheduled_for"] == "2026-08-01"


@pytest.mark.asyncio
async def test_create_suggestion_rejects_foreign_item(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])
    foreign = await _make_foreign_item(db_session)

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id), str(foreign.id)], "occasion": "casual"},
        headers=auth_headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["error_code"] == "OUTFIT_ITEM_OWNERSHIP"


@pytest.mark.asyncio
async def test_create_suggestion_rejects_invalid_occasion(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id)], "occasion": "space-walk"},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_suggestion_rejects_unknown_fields(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id)], "occasion": "casual", "source": "manual"},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_suggestion_validates_attribute_bounds(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])

    too_many_colors = await client.post(
        "/api/v1/outfits/suggestions",
        json={
            "items": [str(shirt.id)],
            "occasion": "casual",
            "palette": [f"color-{i}" for i in range(11)],
        },
        headers=auth_headers,
    )
    assert too_many_colors.status_code == 422, too_many_colors.text

    oversized_notes = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id)], "occasion": "casual", "notes": "x" * 2001},
        headers=auth_headers,
    )
    assert oversized_notes.status_code == 422, oversized_notes.text


@pytest.mark.asyncio
async def test_create_suggestion_available_with_ai_off(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    resp = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id), str(jeans.id)], "occasion": "casual"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "external"


@pytest.mark.asyncio
async def test_suggestion_listed_under_external_source_filter(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    created = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id), str(jeans.id)], "occasion": "casual"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    outfit_id = created.json()["id"]

    listed = await client.get("/api/v1/outfits?source=external", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert outfit_id in [o["id"] for o in listed.json()["outfits"]]


@pytest.mark.asyncio
async def test_suggestion_not_listed_as_pairing(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    created = await client.post(
        "/api/v1/outfits/suggestions",
        json={"items": [str(shirt.id), str(jeans.id)], "occasion": "casual"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    pairings = await client.get("/api/v1/pairings", headers=auth_headers)
    assert pairings.status_code == 200, pairings.text
    assert created.json()["id"] not in [p["id"] for p in pairings.json()["pairings"]]


# --- POST /pairings/item/{item_id} ------------------------------------------


@pytest.mark.asyncio
async def test_create_pairing_persists_external_pairing(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans, jacket = await _make_wardrobe(db_session, test_user, ["shirt", "jeans", "jacket"])

    resp = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={
            "items": [str(jeans.id), str(jacket.id)],
            "reasoning": "Denim anchors the shirt",
            "style_notes": "Keep the jacket open",
            "season": "fall",
            "formality": "smart-casual",
            "palette": ["blue", "grey"],
            "notes": "Good transitional-weather pick",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "external"
    assert body["occasion"] == "pairing"
    assert body["source_item"]["id"] == str(shirt.id)
    assert body["season"] == "fall"
    assert body["formality"] == "smart-casual"
    assert body["palette"] == ["blue", "grey"]
    assert body["notes"] == "Good transitional-weather pick"
    # The source item leads when left out of the partner list
    assert [i["id"] for i in body["items"]] == [str(shirt.id), str(jeans.id), str(jacket.id)]


@pytest.mark.asyncio
async def test_create_pairing_respects_explicit_source_position(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans, jacket = await _make_wardrobe(db_session, test_user, ["shirt", "jeans", "jacket"])

    resp = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(jeans.id), str(shirt.id), str(jacket.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [i["id"] for i in body["items"]] == [str(jeans.id), str(shirt.id), str(jacket.id)]


@pytest.mark.asyncio
async def test_create_pairing_unknown_source_item_404(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (jeans,) = await _make_wardrobe(db_session, test_user, ["jeans"])

    resp = await client.post(
        f"/api/v1/pairings/item/{uuid4()}",
        json={"items": [str(jeans.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_create_pairing_rejects_foreign_partner(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])
    foreign = await _make_foreign_item(db_session)

    resp = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(foreign.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["error_code"] == "OUTFIT_ITEM_OWNERSHIP"


@pytest.mark.asyncio
async def test_create_pairing_requires_a_partner(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    (shirt,) = await _make_wardrobe(db_session, test_user, ["shirt"])

    resp = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(shirt.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_create_pairing_available_with_ai_off(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    resp = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(jeans.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "external"


# --- Pairing list/delete inclusion ------------------------------------------


@pytest.mark.asyncio
async def test_external_pairing_listed_alongside_generated(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    created = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(jeans.id)]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    pairing_id = created.json()["id"]

    all_pairings = await client.get("/api/v1/pairings", headers=auth_headers)
    assert all_pairings.status_code == 200, all_pairings.text
    assert pairing_id in [p["id"] for p in all_pairings.json()["pairings"]]

    item_pairings = await client.get(f"/api/v1/pairings/item/{shirt.id}", headers=auth_headers)
    assert item_pairings.status_code == 200, item_pairings.text
    assert pairing_id in [p["id"] for p in item_pairings.json()["pairings"]]


@pytest.mark.asyncio
async def test_generated_pairing_listing_unchanged(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    outfit = Outfit(
        user_id=test_user.id,
        occasion="pairing",
        scheduled_for=date.today(),
        status=OutfitStatus.pending,
        source=OutfitSource.pairing,
        source_item_id=shirt.id,
        reasoning="Generated pairing",
    )
    outfit.items.append(OutfitItem(item_id=shirt.id, position=0))
    outfit.items.append(OutfitItem(item_id=jeans.id, position=1))
    db_session.add(outfit)
    await db_session.commit()

    listed = await client.get("/api/v1/pairings", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    entries = [p for p in listed.json()["pairings"] if p["id"] == str(outfit.id)]
    assert len(entries) == 1
    # Default-on regression: internally-generated rows report the attributes as null
    assert entries[0]["season"] is None
    assert entries[0]["formality"] is None
    assert entries[0]["palette"] is None
    assert entries[0]["notes"] is None


@pytest.mark.asyncio
async def test_delete_external_pairing(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    created = await client.post(
        f"/api/v1/pairings/item/{shirt.id}",
        json={"items": [str(jeans.id)]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    pairing_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/pairings/{pairing_id}", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text

    listed = await client.get("/api/v1/pairings", headers=auth_headers)
    assert pairing_id not in [p["id"] for p in listed.json()["pairings"]]


@pytest.mark.asyncio
async def test_external_pairing_survives_source_item_deletion(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    # DELETE /items/{id} hard-deletes, and Outfit.source_item_id is ON DELETE SET NULL,
    # so the row must stay classifiable as a pairing without leaning on source_item_id.
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])
    shirt_id, jeans_id = shirt.id, jeans.id

    created = await client.post(
        f"/api/v1/pairings/item/{shirt_id}",
        json={"items": [str(jeans_id)]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    pairing_id = created.json()["id"]

    removed = await client.delete(f"/api/v1/items/{shirt_id}", headers=auth_headers)
    assert removed.status_code == 204, removed.text

    listed = await client.get("/api/v1/pairings", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert pairing_id in [p["id"] for p in listed.json()["pairings"]]

    deleted = await client.delete(f"/api/v1/pairings/{pairing_id}", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text


@pytest.mark.asyncio
async def test_generated_pairing_survives_source_item_deletion(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])
    shirt_id, jeans_id = shirt.id, jeans.id
    outfit_id = uuid4()

    outfit = Outfit(
        id=outfit_id,
        user_id=test_user.id,
        occasion="pairing",
        scheduled_for=date.today(),
        status=OutfitStatus.pending,
        source=OutfitSource.pairing,
        source_item_id=shirt_id,
    )
    outfit.items.append(OutfitItem(item_id=shirt_id, position=0))
    outfit.items.append(OutfitItem(item_id=jeans_id, position=1))
    db_session.add(outfit)
    await db_session.commit()
    # The API shares this session in tests; drop the hand-built rows from the identity map so the
    # request sees what a fresh production session would, rather than OutfitItem objects the
    # cascade has already deleted underneath it.
    db_session.expunge_all()

    removed = await client.delete(f"/api/v1/items/{shirt_id}", headers=auth_headers)
    assert removed.status_code == 204, removed.text

    listed = await client.get("/api/v1/pairings", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert str(outfit_id) in [p["id"] for p in listed.json()["pairings"]]


# --- POST /outfits/studio ----------------------------------------------------


@pytest.mark.asyncio
async def test_studio_accepts_authoring_attributes(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    shirt, jeans = await _make_wardrobe(db_session, test_user, ["shirt", "jeans"])

    resp = await client.post(
        "/api/v1/outfits/studio",
        json={
            "items": [str(shirt.id), str(jeans.id)],
            "occasion": "casual",
            "season": "spring",
            "formality": "casual",
            "palette": ["green"],
            "notes": "Studio compose with attributes",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "manual"
    assert body["season"] == "spring"
    assert body["formality"] == "casual"
    assert body["palette"] == ["green"]
    assert body["notes"] == "Studio compose with attributes"
