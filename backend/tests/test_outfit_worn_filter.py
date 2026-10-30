from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outfit import Outfit, OutfitSource, OutfitStatus, UserFeedback

OUTFITS = {
    "worn-from-lookbook": (OutfitStatus.pending, date.today(), True, date.today(), None),
    "worn-suggestion": (OutfitStatus.accepted, date.today(), True, date.today(), True),
    "said-not-worn": (OutfitStatus.accepted, date.today(), True, date.today(), False),
    "accepted-not-worn": (OutfitStatus.accepted, date.today(), True, None, None),
    "pending": (OutfitStatus.pending, date.today(), None, None, None),
    "lookbook": (OutfitStatus.pending, None, None, None, None),
}


async def _seed(db_session: AsyncSession, user_id) -> dict[str, str]:
    outfits = {}
    for key, (outfit_status, scheduled_for, accepted, worn_at, actually_worn) in OUTFITS.items():
        outfit = Outfit(
            user_id=user_id,
            occasion="casual",
            scheduled_for=scheduled_for,
            status=outfit_status,
            source=OutfitSource.manual,
        )
        if accepted is not None:
            outfit.feedback = UserFeedback(
                accepted=accepted, worn_at=worn_at, actually_worn=actually_worn
            )
        outfits[key] = outfit
    db_session.add_all(outfits.values())
    await db_session.commit()
    return {str(outfit.id): key for key, outfit in outfits.items()}


@pytest.mark.parametrize("entry_point", ["list", "bulk-delete"])
@pytest.mark.parametrize(
    ("worn", "expected"),
    [
        (True, {"worn-from-lookbook", "worn-suggestion"}),
        (False, {"said-not-worn", "accepted-not-worn", "pending"}),
    ],
)
async def test_worn_filter_matches_outfits_with_a_wear_date(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    auth_headers,
    entry_point,
    worn,
    expected,
):
    user_id = test_user.id
    keys_by_id = await _seed(db_session, user_id)
    filters = {"worn": worn, "is_lookbook": False}

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

    assert {keys_by_id[outfit_id] for outfit_id in matched} == expected
