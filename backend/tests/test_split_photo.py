"""Splitting a photo with several garments: the reply parser, the crop, and the two endpoints."""

import asyncio
import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models.item import ClothingItem, ItemStatus
from app.models.preference import UserPreference
from app.models.user import User
from app.services.ai_service import DETECTION_PROMPT, AIService
from app.services.garment_detector import (
    DETECTION_EXAMPLE,
    MAX_GARMENTS,
    DetectedGarment,
    parse_detection,
)
from app.services.image_service import ImageService


def _reply(*garments: dict) -> str:
    return json.dumps({"garments": list(garments)})


def _g(left, top, right, bottom, type_="shirt", colors=("blue",)) -> dict:
    return {
        "type": type_,
        "colors": list(colors),
        "box": {"left": left, "top": top, "right": right, "bottom": bottom},
    }


ANSWER = _reply(_g(10, 20, 40, 80), _g(55, 20, 90, 80))
ANSWER_BOXES = [(0.1, 0.2, 0.4, 0.8), (0.55, 0.2, 0.9, 0.8)]
HALF = (0.0, 0.0, 0.5, 0.5)
EMPTY = '{"garments": []}'
EXAMPLE = json.dumps(DETECTION_EXAMPLE)


class TestParseDetection:
    def test_reads_percent_boxes_into_fractions(self):
        [shirt] = parse_detection(_reply(_g(10, 20, 60, 80)))

        assert shirt.type == "shirt"
        assert shirt.colors == ["blue"]
        assert (shirt.left, shirt.top) == pytest.approx((0.1, 0.2))
        assert (shirt.width, shirt.height) == pytest.approx((0.5, 0.6))

    def test_reads_fraction_boxes_when_every_value_is_at_most_one(self):
        [shirt] = parse_detection(_reply(_g(0.1, 0.2, 0.6, 0.8)))

        assert (shirt.left, shirt.width) == pytest.approx((0.1, 0.5))

    def test_a_fraction_box_that_overflows_an_edge_is_clamped_not_dropped(self):
        [shirt] = parse_detection(_reply(_g(0.6, 0.1, 1.03, 0.9)))

        assert (shirt.left, shirt.top) == pytest.approx((0.6, 0.1))
        assert (shirt.width, shirt.height) == pytest.approx((0.4, 0.8))

    def test_reads_a_box_given_as_a_list(self):
        reply = json.dumps({"garments": [{"type": "jeans", "box": [10, 10, 50, 90]}]})

        [jeans] = parse_detection(reply)

        assert jeans.type == "jeans"
        assert jeans.width == pytest.approx(0.4)

    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            (json.dumps([_g(0, 0, 50, 50)]), [HALF]),
            ("Here you go:\n```json\n" + _reply(_g(0, 0, 50, 50)) + "\n```", [HALF]),
            ("Box format [l,t,r,b]; {shirt} found. " + ANSWER, ANSWER_BOXES),
            (f"With no clothing I would return {EMPTY}. Answer: {ANSWER}", ANSWER_BOXES),
            (f"```json\n{EMPTY}\n```\n```json\n{ANSWER}\n```", ANSWER_BOXES),
            (f"The example was {EXAMPLE}. Mine: {ANSWER}", ANSWER_BOXES),
            (f"Like {EXAMPLE} but as a list: {json.dumps([_g(0, 0, 50, 50)])}", [HALF]),
            (_reply(_g(100, 200, 600, 800)), [(0.1, 0.2, 0.6, 0.8)]),
            (
                json.dumps({"garments": [{"type": "shirt", "box_2d": [200, 100, 800, 600]}]}),
                [(0.1, 0.2, 0.6, 0.8)],
            ),
            (
                _reply(_g(41, 39, 330, 95), _g(340, 41, 670, 94), _g(681, 42, 972, 95)),
                [(0.041, 0.39, 0.33, 0.95), (0.34, 0.41, 0.67, 0.94), (0.681, 0.42, 0.972, 0.95)],
            ),
            (
                "```json\n"
                + _reply(_g(5, 30, 30, 90), _g(35, 40, 65, 88), _g(70, 45, 95, 88))
                + "\n```",
                [(0.05, 0.3, 0.3, 0.9), (0.35, 0.4, 0.65, 0.88), (0.7, 0.45, 0.95, 0.88)],
            ),
            (f"[]\n{ANSWER}", ANSWER_BOXES),
            (f"Example {EXAMPLE}. Answer: {EMPTY}", []),
            (f"```json\n{ANSWER}\n```\nIf none I would return {EMPTY}", ANSWER_BOXES),
        ],
        ids=[
            "bare-list",
            "fenced",
            "brackets-and-braces-in-reasoning",
            "empty-example-echoed-in-prose",
            "empty-example-echoed-fenced",
            "shirt-example-echoed",
            "shirt-example-then-bare-list",
            "per-mille",
            "box-2d",
            "per-mille-x-percent-y",
            "fenced-percent-three-garments",
            "empty-list-before-answer",
            "shirt-example-then-real-empty-answer",
            "fenced-answer-then-empty-in-prose",
        ],
    )
    def test_reads_the_answer_out_of_the_reply(self, reply, expected):
        edges = [
            (g.left, g.top, g.left + g.width, g.top + g.height) for g in parse_detection(reply)
        ]

        assert edges == [pytest.approx(e) for e in expected]

    def test_the_prompt_shows_the_example_the_parser_ignores(self):
        assert json.dumps(DETECTION_EXAMPLE) in DETECTION_PROMPT
        assert "<<" not in DETECTION_PROMPT

    def test_clamps_boxes_into_the_photo(self):
        [shirt] = parse_detection(_reply(_g(-10, -5, 130, 120)))

        assert (shirt.left, shirt.top, shirt.width, shirt.height) == (0.0, 0.0, 1.0, 1.0)

    def test_swaps_inverted_corners(self):
        [shirt] = parse_detection(_reply(_g(60, 80, 10, 20)))

        assert (shirt.left, shirt.top) == pytest.approx((0.1, 0.2))
        assert (shirt.width, shirt.height) == pytest.approx((0.5, 0.6))

    @pytest.mark.parametrize("box", [(10, 10, 12, 50), (10, 10, 50, 12), (30, 30, 30, 60)])
    def test_drops_specks_and_flat_boxes(self, box):
        assert parse_detection(_reply(_g(*box))) == []

    def test_drops_a_box_that_is_the_same_garment_again(self):
        reply = _reply(_g(10, 10, 60, 90), _g(11, 11, 61, 91), _g(65, 10, 95, 90))

        assert len(parse_detection(reply)) == 2

    def test_keeps_garments_that_only_touch(self):
        reply = _reply(_g(0, 0, 50, 100), _g(50, 0, 100, 100))

        assert len(parse_detection(reply)) == 2

    def test_caps_the_list(self):
        reply = _reply(*[_g(i * 10, 0, i * 10 + 9, 50) for i in range(10)])

        assert len(parse_detection(reply)) == MAX_GARMENTS

    def test_an_unknown_type_is_kept_as_unknown(self):
        [g] = parse_detection(_reply(_g(0, 0, 50, 50, type_="culottes")))

        assert g.type == "unknown"

    def test_colours_are_normalised_and_deduplicated(self):
        [g] = parse_detection(_reply(_g(0, 0, 50, 50, colors=("Blue", "blue", 3, "nonsense"))))

        assert g.colors == ["blue"]

    @pytest.mark.parametrize(
        "reply",
        [
            "",
            "I cannot help with that",
            "{not json",
            "[]",
            '{"garments": "none"}',
            '{"garments": [1, "a", null]}',
            _reply({"type": "shirt"}),
            _reply({"type": "shirt", "box": {"left": "x", "top": 1, "right": 2, "bottom": 3}}),
            _reply({"type": "shirt", "box": [1, 2, 3]}),
            _reply({"type": "shirt", "box": {"left": True, "top": 0, "right": 50, "bottom": 50}}),
        ],
    )
    def test_unusable_replies_give_no_garments(self, reply):
        assert parse_detection(reply) == []


class TestCropToJpeg:
    @staticmethod
    def _store(size=(400, 600)) -> tuple[ImageService, str]:
        service = ImageService()
        (service.storage_path / "crops").mkdir(parents=True, exist_ok=True)
        path = f"crops/{uuid4()}.jpg"
        image = Image.new("RGB", size, (255, 255, 255))
        image.paste(Image.new("RGB", (100, 200), (255, 0, 0)), (100, 100))
        image.save(service.storage_path / path, format="JPEG", quality=95)
        return service, path

    def test_crops_the_box_with_a_little_room_round_it(self):
        service, path = self._store()

        data = service.crop_to_jpeg(path, 0.25, 100 / 600, 0.25, 200 / 600)

        with Image.open(BytesIO(data)) as crop:
            # 100x200 box plus 2% of the long side (4px) on every edge, give or take rounding
            assert abs(crop.width - 108) <= 2
            assert abs(crop.height - 208) <= 2
            assert crop.getpixel((crop.width // 2, crop.height // 2))[0] > 200

    def test_a_box_at_the_edge_stays_inside_the_photo(self):
        service, path = self._store()

        data = service.crop_to_jpeg(path, 0.0, 0.0, 1.0, 1.0)

        with Image.open(BytesIO(data)) as crop:
            assert crop.size == (400, 600)

    def test_a_missing_photo_is_an_error(self):
        with pytest.raises(ValueError, match="not found"):
            ImageService().crop_to_jpeg("nowhere/missing.jpg", 0, 0, 0.5, 0.5)


def _jpeg_bytes(size=(400, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (200, 200, 200)).save(buf, format="JPEG")
    return buf.getvalue()


async def _make_item(db_session: AsyncSession, user: User, **overrides) -> ClothingItem:
    paths = await ImageService().process_and_store(
        user_id=user.id, image_data=_jpeg_bytes(), original_filename="test.jpg"
    )
    item = ClothingItem(
        user_id=user.id,
        type="shirt",
        image_path=paths["image_path"],
        medium_path=paths["medium_path"],
        thumbnail_path=paths["thumbnail_path"],
        image_hash=paths["image_hash"],
        **{"status": ItemStatus.ready, **overrides},
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _detects(garments=None, error=None):
    return patch.object(
        AIService,
        "detect_garments",
        AsyncMock(side_effect=error, return_value=garments if garments is not None else []),
    )


class TestDetectGarmentsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_the_detected_boxes_and_writes_nothing(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)
        found = [
            DetectedGarment("shirt", ["blue"], 0.1, 0.1, 0.4, 0.3),
            DetectedGarment("jeans", [], 0.1, 0.5, 0.4, 0.4),
        ]

        with _detects(found):
            response = await client.post(
                f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
            )

        assert response.status_code == 200
        garments = response.json()["garments"]
        assert [g["type"] for g in garments] == ["shirt", "jeans"]
        assert garments[0] == {
            "type": "shirt",
            "colors": ["blue"],
            "left": 0.1,
            "top": 0.1,
            "width": 0.4,
            "height": 0.3,
        }
        assert len(await _all_items(db_session, test_user)) == 1

    @pytest.mark.asyncio
    async def test_no_garments_found_is_an_empty_list_not_an_error(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)

        with _detects([]):
            response = await client.post(
                f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json() == {"garments": []}

    @pytest.mark.asyncio
    async def test_unknown_item_is_404(self, client: AsyncClient, auth_headers):
        response = await client.post(
            f"/api/v1/items/{uuid4()}/detect-garments", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_another_users_item_is_404(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers
    ):
        other = User(
            id=uuid4(),
            external_id=f"other-{uuid4()}",
            email=f"other-{uuid4()}@example.com",
            display_name="Other",
            timezone="UTC",
            is_active=True,
            onboarding_completed=False,
        )
        db_session.add(other)
        await db_session.commit()
        item = await _make_item(db_session, other)

        response = await client.post(
            f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_vision_off_is_503_without_calling_the_ai_or_spending_the_quota(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)
        limiter = AsyncMock()

        with (
            patch.object(get_settings(), "ai_vision_enabled", False),
            patch.object(get_settings(), "ai_text_enabled", True),
            patch("app.api.split.rate_limit_by_user", limiter),
            _detects([]) as detect,
        ):
            response = await client.post(
                f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
            )

        assert response.status_code == 503
        assert response.json()["detail"]["error_code"] == "AI_VISION_DISABLED"
        detect.assert_not_awaited()
        limiter.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unreachable_ai_is_502(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)

        with _detects(error=RuntimeError("down")):
            response = await client.post(
                f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
            )

        assert response.status_code == 502
        assert response.json()["detail"]["error_code"] == "AI_UNREACHABLE"

    @pytest.mark.asyncio
    async def test_uses_the_users_own_ai_endpoints(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)
        db_session.add(
            UserPreference(
                user_id=test_user.id,
                ai_endpoints=[
                    {"url": "http://users-own-ai:11434/v1", "name": "mine", "enabled": True}
                ],
            )
        )
        await db_session.commit()

        with patch.object(AIService, "detect_garments", autospec=True, return_value=[]) as detect:
            response = await client.post(
                f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
            )

        assert response.status_code == 200
        [call] = detect.await_args_list
        assert call.args[0]._endpoints[0].url == "http://users-own-ai:11434/v1"

    @pytest.mark.asyncio
    async def test_is_rate_limited(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        item = await _make_item(db_session, test_user)

        with _detects([]):
            codes = [
                (
                    await client.post(
                        f"/api/v1/items/{item.id}/detect-garments", headers=auth_headers
                    )
                ).status_code
                for _ in range(11)
            ]

        assert codes[:10] == [200] * 10
        assert codes[10] == 429

    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        response = await client.post(f"/api/v1/items/{uuid4()}/detect-garments")

        assert response.status_code in (401, 403)


BOXES = [
    {"left": 0.05, "top": 0.05, "width": 0.4, "height": 0.4},
    {"left": 0.5, "top": 0.5, "width": 0.4, "height": 0.4},
]


def _redis():
    redis = MagicMock()
    job = MagicMock()
    job.job_id = "job-1"
    redis.enqueue_job = AsyncMock(return_value=job)
    redis.aclose = AsyncMock()
    return redis


def _vision(enabled: bool):
    return MagicMock(effective_ai_vision_enabled=enabled)


async def _all_items(db_session: AsyncSession, user: User | UUID) -> list[ClothingItem]:
    user_id = user if isinstance(user, UUID) else user.id
    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.user_id == user_id))
    return list(result.scalars().all())


class TestSplitEndpoint:
    @pytest.mark.asyncio
    async def test_creates_one_item_per_box_queues_tagging_and_archives_the_source(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        source = await _make_item(db_session, test_user)
        redis = _redis()

        with (
            patch("app.api.split.settings", _vision(True)),
            patch("app.api.split.create_pool", AsyncMock(return_value=redis)),
        ):
            response = await client.post(
                f"/api/v1/items/{source.id}/split", json={"boxes": BOXES}, headers=auth_headers
            )

        assert response.status_code == 201
        body = response.json()
        assert body["source_id"] == str(source.id)
        assert len(body["item_ids"]) == 2

        items = await _all_items(db_session, test_user)
        by_id = {str(i.id): i for i in items}
        refreshed = by_id[str(source.id)]
        assert refreshed.is_archived and refreshed.archive_reason == "split"
        assert refreshed.status == ItemStatus.archived

        service = ImageService()
        for item_id in body["item_ids"]:
            new = by_id[item_id]
            assert new.type == "unknown" and not new.is_archived
            assert new.status == ItemStatus.processing and new.ai_job_id == "job-1"
            assert (service.storage_path / new.image_path).exists()
            assert new.image_path != source.image_path

        assert redis.enqueue_job.await_count == 2
        for call in redis.enqueue_job.await_args_list:
            assert call.args[0] == "tag_item_image"
            assert call.kwargs["_queue_name"] == "arq:tagging"

    @pytest.mark.asyncio
    async def test_identical_boxes_are_not_rejected_as_duplicates(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        # The photo is one flat colour, so both crops hash alike: exactly what the upload
        # duplicate check would reject. A split must not run it.
        source = await _make_item(db_session, test_user)

        with (
            patch("app.api.split.settings", _vision(True)),
            patch("app.api.split.create_pool", AsyncMock(return_value=_redis())),
        ):
            response = await client.post(
                f"/api/v1/items/{source.id}/split",
                json={"boxes": [BOXES[0], BOXES[0]]},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert len(response.json()["item_ids"]) == 2

    @pytest.mark.asyncio
    async def test_the_new_items_are_cropped_from_the_boxes(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        source = await _make_item(db_session, test_user)

        with (
            patch("app.api.split.settings", _vision(False)),
        ):
            response = await client.post(
                f"/api/v1/items/{source.id}/split",
                json={"boxes": [{"left": 0, "top": 0, "width": 0.5, "height": 0.5}]},
                headers=auth_headers,
            )

        [new_id] = response.json()["item_ids"]
        new = next(i for i in await _all_items(db_session, test_user) if str(i.id) == new_id)
        with Image.open(ImageService().storage_path / new.image_path) as crop:
            # half of a 400x600 photo, plus the 2% padding on the sides that are not at an edge
            assert 200 <= crop.width <= 212
            assert 300 <= crop.height <= 318

    @pytest.mark.asyncio
    async def test_with_ai_vision_off_the_new_items_are_ready_and_nothing_is_queued(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        source = await _make_item(db_session, test_user)

        with (
            patch("app.api.split.settings", _vision(False)),
            patch("app.api.split.create_pool", AsyncMock(side_effect=AssertionError)),
        ):
            response = await client.post(
                f"/api/v1/items/{source.id}/split", json={"boxes": BOXES}, headers=auth_headers
            )

        assert response.status_code == 201
        ids = set(response.json()["item_ids"])
        new = [i for i in await _all_items(db_session, test_user) if str(i.id) in ids]
        assert len(new) == 2 and all(i.status == ItemStatus.ready for i in new)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("pool_error", "enqueue_errors", "expected_jobs"),
        [
            (ConnectionError, [], [None, None]),
            (None, [None, ConnectionError, None], ["job-1", None, "job-1"]),
        ],
        ids=["redis-down", "one-enqueue-fails"],
    )
    async def test_a_queueing_failure_still_creates_the_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        auth_headers,
        pool_error,
        enqueue_errors,
        expected_jobs,
    ):
        source = await _make_item(db_session, test_user)
        redis = _redis()
        job = redis.enqueue_job.return_value
        redis.enqueue_job.side_effect = [error or job for error in enqueue_errors] or None
        boxes = [{"left": 0.3 * i, "top": 0.1, "width": 0.25, "height": 0.5} for i in range(3)]

        with (
            patch("app.api.split.settings", _vision(True)),
            patch(
                "app.api.split.create_pool", AsyncMock(side_effect=pool_error, return_value=redis)
            ),
        ):
            response = await client.post(
                f"/api/v1/items/{source.id}/split",
                json={"boxes": boxes[: len(expected_jobs)]},
                headers=auth_headers,
            )

        assert response.status_code == 201
        ids = response.json()["item_ids"]
        assert redis.enqueue_job.await_count == len(enqueue_errors)
        by_id = {str(i.id): i for i in await _all_items(db_session, test_user)}
        assert [by_id[i].ai_job_id for i in ids] == expected_jobs
        assert all(by_id[i].status == ItemStatus.processing for i in ids)

    @pytest.mark.asyncio
    async def test_a_failure_part_way_creates_nothing_and_removes_the_files(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        source = await _make_item(db_session, test_user)
        source_id, user_id = source.id, test_user.id
        service = ImageService()
        before = sorted(p.name for p in (service.storage_path / str(user_id)).iterdir())
        real = ImageService.process_and_store
        calls = {"n": 0}

        async def flaky(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return await real(self, **kwargs)

        with (
            patch("app.api.split.settings", _vision(True)),
            patch.object(ImageService, "process_and_store", flaky),
        ):
            with pytest.raises(RuntimeError, match="disk full"):
                await client.post(
                    f"/api/v1/items/{source_id}/split", json={"boxes": BOXES}, headers=auth_headers
                )

        items = await _all_items(db_session, user_id)
        assert [i.id for i in items] == [source_id]
        assert not items[0].is_archived
        after = sorted(p.name for p in (service.storage_path / str(user_id)).iterdir())
        assert after == before

    @pytest.mark.asyncio
    async def test_a_box_outside_the_photo_is_rejected(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        source = await _make_item(db_session, test_user)

        response = await client.post(
            f"/api/v1/items/{source.id}/split",
            json={"boxes": [{"left": 0.8, "top": 0.1, "width": 0.5, "height": 0.2}]},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [0, 9])
    async def test_the_number_of_boxes_is_limited(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers, count
    ):
        source = await _make_item(db_session, test_user)

        response = await client.post(
            f"/api/v1/items/{source.id}/split",
            json={"boxes": [BOXES[0]] * count},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("state", "expected_status", "error_code"),
        [
            ({"is_archived": True, "status": ItemStatus.archived}, 409, "SOURCE_ARCHIVED"),
            ({"status": ItemStatus.processing, "processing_kind": "rotate"}, 409, "SOURCE_BUSY"),
            (
                {"status": ItemStatus.processing, "processing_kind": "background_removal"},
                409,
                "SOURCE_BUSY",
            ),
            ({"status": ItemStatus.processing, "processing_kind": None}, 201, None),
        ],
        ids=["archived", "rotating", "removing-background", "being-tagged"],
    )
    async def test_the_sources_state_decides_whether_it_can_be_split(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        auth_headers,
        state,
        expected_status,
        error_code,
    ):
        source = await _make_item(db_session, test_user, **state)

        with patch("app.api.split.settings", _vision(False)):
            response = await client.post(
                f"/api/v1/items/{source.id}/split", json={"boxes": BOXES}, headers=auth_headers
            )

        assert response.status_code == expected_status
        if error_code is not None:
            assert response.json()["detail"]["error_code"] == error_code
            assert len(await _all_items(db_session, test_user)) == 1

    @pytest.mark.asyncio
    async def test_two_splits_at_once_make_one_set_of_items(
        self, client: AsyncClient, db_session: AsyncSession, session_maker, test_user, auth_headers
    ):
        # The `client` fixture puts every request on one shared session, which cannot show
        # row-lock contention, so each request here gets a connection of its own.
        source = await _make_item(db_session, test_user)

        async def own_session():
            async with session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = own_session
        with patch("app.api.split.settings", _vision(False)):
            responses = await asyncio.gather(
                *(
                    client.post(
                        f"/api/v1/items/{source.id}/split",
                        json={"boxes": BOXES},
                        headers=auth_headers,
                    )
                    for _ in range(2)
                )
            )

        assert sorted(r.status_code for r in responses) == [201, 409]
        [refused] = [r for r in responses if r.status_code == 409]
        assert refused.json()["detail"]["error_code"] == "SOURCE_ARCHIVED"
        items = await _all_items(db_session, test_user)
        assert len([i for i in items if not i.is_archived]) == len(BOXES)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "body"), [("detect-garments", None), ("split", {"boxes": BOXES})]
    )
    async def test_a_missing_photo_file_is_404_without_leaking_the_path(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers, action, body
    ):
        source = await _make_item(db_session, test_user)
        (ImageService().storage_path / source.image_path).unlink()

        with patch("app.api.split.settings", _vision(False)), _detects([]) as detect:
            response = await client.post(
                f"/api/v1/items/{source.id}/{action}", json=body, headers=auth_headers
            )

        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "IMAGE_NOT_FOUND"
        assert source.image_path not in response.text
        detect.assert_not_awaited()
        assert len(await _all_items(db_session, test_user)) == 1

    @pytest.mark.asyncio
    async def test_unknown_item_is_404(self, client: AsyncClient, auth_headers):
        response = await client.post(
            f"/api/v1/items/{uuid4()}/split", json={"boxes": BOXES}, headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        response = await client.post(f"/api/v1/items/{uuid4()}/split", json={"boxes": BOXES})

        assert response.status_code in (401, 403)


class TestArchivedWhileAnalysing:
    @pytest.mark.asyncio
    async def test_a_split_source_still_being_tagged_stays_archived(
        self, db_session: AsyncSession, test_user
    ):
        from app.services.ai_service import ClothingTags
        from app.workers import tagging

        item = await _make_item(db_session, test_user, is_archived=True)
        item.status = ItemStatus.archived
        await db_session.commit()
        item_id = item.id

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path, locale="en"):
                return ClothingTags(type="shirt", primary_color="blue", colors=["blue"])

        with (
            patch.object(tagging, "AIService", _StubAI),
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item_id), __file__)

        assert result["status"] == "success"
        [done] = [i for i in await _all_items(db_session, test_user) if i.id == item_id]
        assert done.status == ItemStatus.archived
        assert done.primary_color == "blue"
