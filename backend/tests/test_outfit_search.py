from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outfit import Outfit, OutfitSource, OutfitStatus

OUTFITS = {
    "percent": ("100% cotton", "office"),
    "underscore": ("my_look", "office"),
    "lookalike": ("myXlook", "office"),
    "named-casual": ("Weekend", "casual"),
    "unnamed-casual": (None, "casual"),
    "unnamed-formal": (None, "formal"),
}


async def _seed(db_session: AsyncSession, user_id) -> dict[str, str]:
    outfits = {
        key: Outfit(
            user_id=user_id,
            name=name,
            occasion=occasion,
            scheduled_for=date.today(),
            status=OutfitStatus.pending,
            source=OutfitSource.manual,
        )
        for key, (name, occasion) in OUTFITS.items()
    }
    db_session.add_all(outfits.values())
    await db_session.commit()
    return {str(outfit.id): key for key, outfit in outfits.items()}


async def _listed(client, auth_headers, search, occasions):
    params = {"search": search}
    if occasions:
        params["occasions"] = ",".join(occasions)
    response = await client.get("/api/v1/outfits", params=params, headers=auth_headers)
    assert response.status_code == 200
    return {outfit["id"] for outfit in response.json()["outfits"]}


async def _bulk_deleted(client, auth_headers, db_session, user_id, search, occasions):
    filters = {"search": search}
    if occasions:
        filters["occasions"] = occasions
    response = await client.post(
        "/api/v1/outfits/bulk/delete",
        json={"select_all": True, "filters": filters},
        headers=auth_headers,
    )
    assert response.status_code == 200
    db_session.expire_all()
    remaining = await db_session.scalars(select(Outfit.id).where(Outfit.user_id == user_id))
    return {str(outfit_id) for outfit_id in remaining}


@pytest.mark.parametrize("entry_point", ["list", "bulk-delete"])
@pytest.mark.parametrize(
    ("search", "occasions", "expected"),
    [
        pytest.param("%", None, {"percent"}, id="percent-is-literal"),
        pytest.param("y_l", None, {"underscore"}, id="underscore-is-literal"),
        pytest.param("weekend", None, {"named-casual"}, id="name-case-insensitive"),
        pytest.param(
            "Freizeit", ["casual"], {"named-casual", "unnamed-casual"}, id="translated-occasion"
        ),
        pytest.param("look", ["formal"], {"underscore", "lookalike", "unnamed-formal"}, id="both"),
    ],
)
async def test_search_matches_names_literally_or_the_given_occasions(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    auth_headers,
    entry_point,
    search,
    occasions,
    expected,
):
    keys_by_id = await _seed(db_session, test_user.id)

    if entry_point == "list":
        matched = await _listed(client, auth_headers, search, occasions)
    else:
        remaining = await _bulk_deleted(
            client, auth_headers, db_session, test_user.id, search, occasions
        )
        matched = set(keys_by_id) - remaining

    assert {keys_by_id[outfit_id] for outfit_id in matched} == expected
