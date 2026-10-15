from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.stylist_service import resolve_citations, wardrobe_listing


def _item(item_type: str, seasons: list[str] | None = None, **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        type=item_type,
        image_path=f"{item_type}.jpg",
        status=ItemStatus.ready,
        season=seasons or [],
        **fields,
    )


class TestStylist:
    def test_citations_become_item_references(self):
        jacket, sneakers = _item("jacket"), _item("sneakers")
        reply = resolve_citations("Prova la giacca [#1] con [#2] e [#9].", [jacket, sneakers])
        assert reply.text == f"Prova la giacca [[item:{jacket.id}]] con [[item:{sneakers.id}]] e ."
        assert reply.items == [jacket, sneakers]

    def test_listing_numbers_every_item(self):
        listing = wardrobe_listing([_item("jeans", ["all-season"], primary_color="blue")])
        assert listing == "1. blue jeans (all-season)"

    @pytest.mark.asyncio
    async def test_chat_endpoint(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
            )
        )
        await db_session.commit()
        with patch(
            "app.services.ai_service.AIService._call_with_fallback",
            AsyncMock(return_value=("Metti i jeans [#1].", None, None)),
        ):
            response = await client.post(
                "/api/v1/stylist",
                json={"messages": [{"role": "user", "content": "Cosa metto oggi?"}]},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["reply"].startswith("Metti i jeans [[item:")
        assert data["items"][0]["type"] == "jeans"

    @pytest.mark.asyncio
    async def test_last_turn_must_be_the_user(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/stylist",
            json={"messages": [{"role": "assistant", "content": "Ciao"}]},
            headers=auth_headers,
        )
        assert response.status_code == 422
