import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.ai_service import (
    AIDisabledError,
    AIResponseTruncatedError,
    AIUnusableResponseError,
    _AIProviderResponseError,
)
from app.workers.tagging import analysis_failure, tag_item_image, update_item_status_to_error
from tests.test_error_codes import ERRORS_EN, icu_arguments

FAILURE = {"error": "boom", "error_code": "AI_ANALYSIS_FAILED", "error_params": {}}
AI_REQUEST = httpx.Request("POST", "http://ai.test/v1/chat/completions")
PHOTO = Path("/data/images/u/x.jpg")


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


class TestUpdateItemStatusToError:
    @pytest.mark.asyncio
    async def test_flips_processing_item_to_error(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/a.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        ctx: dict = {}
        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await update_item_status_to_error(ctx, str(item.id), FAILURE)

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.ai_raw_response == FAILURE

    @pytest.mark.asyncio
    async def test_noop_when_item_already_moved_past_processing(
        self, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/b.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        ctx: dict = {}
        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await update_item_status_to_error(ctx, str(item.id), FAILURE)

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.ai_raw_response is None


FAILURES = [
    (
        AIResponseTruncatedError("cut off", retryable=False, max_tokens=4096),
        "AI_RESPONSE_EMPTY",
        {"max_tokens": 4096},
    ),
    (_AIProviderResponseError("model qwen2.5vl not found"), "AI_PROVIDER_ERROR", {}),
    (AIUnusableResponseError("AI returned nothing usable"), "AI_RESPONSE_UNUSABLE", {}),
    (
        httpx.HTTPStatusError(
            "404 Not Found", request=AI_REQUEST, response=httpx.Response(404, request=AI_REQUEST)
        ),
        "AI_HTTP_ERROR",
        {"status": 404},
    ),
    (httpx.ReadTimeout("timed out", request=AI_REQUEST), "AI_TIMEOUT", {}),
    (httpx.DecodingError("bad gzip", request=AI_REQUEST), "AI_RESPONSE_UNUSABLE", {}),
    (httpx.ConnectError("refused", request=AI_REQUEST), "AI_UNREACHABLE", {}),
    (TimeoutError(), "ANALYSIS_TIMED_OUT", {}),
    (
        FileNotFoundError(2, "No such file or directory", str(PHOTO)),
        "IMAGE_FILE_MISSING",
        {},
    ),
    (AIDisabledError("Internal AI is disabled"), "AI_VISION_DISABLED", {}),
    (ValueError("boom"), "AI_ANALYSIS_FAILED", {}),
]


class TestAnalysisFailure:
    @pytest.mark.parametrize(
        ("exc", "code", "params"), FAILURES, ids=[code for _, code, _ in FAILURES]
    )
    def test_each_failure_gets_a_code_with_its_message_arguments(self, exc, code, params):
        catalog = json.loads(ERRORS_EN.read_text())

        failure = analysis_failure(exc, PHOTO)

        assert failure["error_code"] == code
        assert failure["error_params"] == params
        assert set(params) == icu_arguments(catalog[code])
        assert failure["error"]

    def test_provider_reply_stays_in_the_english_text(self):
        failure = analysis_failure(_AIProviderResponseError("model qwen2.5vl not found"), PHOTO)

        assert failure["error"] == "model qwen2.5vl not found"

    def test_empty_message_falls_back_to_the_exception_name(self):
        assert analysis_failure(TimeoutError(), PHOTO)["error"] == "TimeoutError"

    def test_missing_photo_does_not_store_its_path(self):
        failure = analysis_failure(FileNotFoundError(2, "No such file", str(PHOTO)), PHOTO)

        assert failure["error"] == "Image not found"

    def test_another_missing_file_is_not_reported_as_the_photo(self):
        failure = analysis_failure(
            FileNotFoundError(2, "No such file", "/etc/ssl/missing-ca.pem"), PHOTO
        )

        assert failure["error_code"] == "AI_ANALYSIS_FAILED"

    def test_result_is_json_serializable(self):
        for exc, _, _ in FAILURES:
            json.dumps(analysis_failure(exc, PHOTO))


class TestMissingPhoto:
    @pytest.mark.asyncio
    async def test_stores_coded_failure_without_the_path(
        self, db_session: AsyncSession, test_user, tmp_path
    ):
        missing = tmp_path / "gone.jpg"
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/gone.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tag_item_image({"job_try": 1}, str(item.id), str(missing))

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.ai_raw_response == {
            "error": "Image not found",
            "error_code": "IMAGE_FILE_MISSING",
            "error_params": {},
        }
