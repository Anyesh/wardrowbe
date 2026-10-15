import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.selfie_service import parse_matches


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 600), (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestParseMatches:
    def test_reads_json_and_ignores_numbers_outside_the_list(self):
        assert parse_matches('Sure! {"matches": [2, 9, 2, 1]}', 3) == [1, 0]

    def test_falls_back_to_bare_numbers(self):
        assert parse_matches("I can see items 3 and 1", 3) == [2, 0]

    def test_empty_answer(self):
        assert parse_matches('{"matches": []}', 5) == []


class TestSelfieApi:
    @pytest.mark.asyncio
    async def test_returns_the_recognised_items(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        items = [
            ClothingItem(
                user_id=test_user.id,
                type=item_type,
                primary_color=color,
                image_path=f"{item_type}.jpg",
                status=ItemStatus.ready,
            )
            for item_type, color in (("jeans", "blue"), ("t-shirt", "white"), ("coat", "black"))
        ]
        db_session.add_all(items)
        await db_session.commit()

        async def fake_call(self, messages, task_name, **kwargs):
            listing = messages[1]["content"][0]["text"]
            wanted = [line.split(".")[0] for line in listing.splitlines()[1:] if "coat" not in line]
            return json.dumps({"matches": [int(n) for n in wanted]}), None, None

        with (
            patch("app.services.ai_service.AIService._call_with_fallback", fake_call),
            patch("app.services.ai_service.AIService._preprocess_image", return_value="aGk="),
        ):
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["considered"] == 3
        assert sorted(i["type"] for i in data["matches"]) == ["jeans", "t-shirt"]

    @pytest.mark.asyncio
    async def test_ai_failure_is_a_clear_error(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
            )
        )
        await db_session.commit()
        with (
            patch(
                "app.services.ai_service.AIService._call_with_fallback",
                AsyncMock(return_value=(None, RuntimeError("down"), None)),
            ),
            patch("app.services.ai_service.AIService._preprocess_image", return_value="aGk="),
        ):
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )
        assert response.status_code == 502
