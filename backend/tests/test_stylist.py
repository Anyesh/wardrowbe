from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.stylist_service import renumber_history, resolve_citations, wardrobe_listing


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

    def test_listing_names_the_subtype(self):
        listing = wardrobe_listing([_item("pants", subtype="chinos", primary_color="beige")])
        assert listing == "1. beige chinos pants"

    def test_earlier_replies_are_renumbered_for_this_listing(self):
        jacket, sneakers, gone = _item("jacket"), _item("sneakers"), _item("coat")
        earlier = f"La giacca [[item:{jacket.id}]] con [[item:{gone.id}]]."
        # The listing changed order since that reply: the jacket is now number 2.
        assert renumber_history(earlier, [sneakers, jacket]) == (
            "La giacca [#2] con (a piece no longer in the wardrobe)."
        )

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
    async def test_follow_ups_send_numbers_not_ids(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        jeans = ClothingItem(
            user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
        )
        db_session.add(jeans)
        await db_session.commit()
        call = AsyncMock(return_value=("Ok [#1].", None, None))
        with patch("app.services.ai_service.AIService._call_with_fallback", call):
            response = await client.post(
                "/api/v1/stylist",
                json={
                    "messages": [
                        {"role": "user", "content": "Cosa metto?"},
                        {"role": "assistant", "content": f"I jeans [[item:{jeans.id}]]."},
                        {"role": "user", "content": "Con cosa li abbino?"},
                    ]
                },
                headers=auth_headers,
            )
        assert response.status_code == 200, response.json()
        sent = call.call_args.args[0]
        assert sent[2] == {"role": "assistant", "content": "I jeans [#1]."}

    @pytest.mark.asyncio
    async def test_newest_pieces_come_first(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        db_session.add_all(
            [
                ClothingItem(
                    user_id=test_user.id,
                    type="coat",
                    image_path="old.jpg",
                    status=ItemStatus.ready,
                    created_at=now - timedelta(days=30),
                ),
                ClothingItem(
                    user_id=test_user.id,
                    type="jeans",
                    image_path="new.jpg",
                    status=ItemStatus.ready,
                    created_at=now,
                ),
            ]
        )
        await db_session.commit()
        call = AsyncMock(return_value=("Ok.", None, None))
        with patch("app.services.ai_service.AIService._call_with_fallback", call):
            await client.post(
                "/api/v1/stylist",
                json={"messages": [{"role": "user", "content": "Ciao"}]},
                headers=auth_headers,
            )
        system = call.call_args.args[0][0]["content"]
        assert system.index("1. jeans") < system.index("2. coat")

    @pytest.mark.asyncio
    async def test_a_piece_archived_meanwhile_is_not_offered(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        jeans = ClothingItem(
            user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
        )
        db_session.add(jeans)
        await db_session.commit()

        async def archive_while_answering(*args, **kwargs):
            jeans.is_archived = True
            await db_session.commit()
            return "Metti i jeans [#1].", None, None

        with patch(
            "app.services.ai_service.AIService._call_with_fallback", archive_while_answering
        ):
            response = await client.post(
                "/api/v1/stylist",
                json={"messages": [{"role": "user", "content": "Cosa metto oggi?"}]},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.json()
        assert response.json()["items"] == []

    @pytest.mark.asyncio
    async def test_text_ai_off_means_no_stylist(self, client: AsyncClient, auth_headers):
        call = AsyncMock()
        with (
            patch("app.api.stylist.get_settings") as settings,
            patch("app.services.ai_service.AIService._call_with_fallback", call),
        ):
            settings.return_value.effective_ai_text_enabled = False
            response = await client.post(
                "/api/v1/stylist",
                json={"messages": [{"role": "user", "content": "Ciao"}]},
                headers=auth_headers,
            )
        assert response.status_code == 503
        call.assert_not_called()

    @pytest.mark.asyncio
    async def test_last_turn_must_be_the_user(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/stylist",
            json={"messages": [{"role": "assistant", "content": "Ciao"}]},
            headers=auth_headers,
        )
        assert response.status_code == 422
