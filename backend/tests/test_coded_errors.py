import pickle
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api import items as items_api
from app.config import get_settings
from app.main import app as main_app
from app.main import coded_http_exception_handler
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services import image_service as image_service_module
from app.services.image_service import ImageService, ImageTooLargeError
from app.services.item_service import TagVocabularyError
from app.services.pairing_service import (
    AIGenerationError,
    InsufficientItemsError,
)
from app.services.recommendation_service import (
    AIRecommendationError,
    InsufficientWardrobeError,
    RecommendationService,
)
from app.services.studio_service import (
    ItemOwnershipError,
    OutfitNotTemplateError,
    OutfitWornImmutableError,
)
from app.services.weather_service import GeocodingServiceError, WeatherServiceError
from app.utils.errors import Coded, CodedHTTPException, CodedValueError, http_error
from app.utils.uploads import UploadTooLargeError
from tests.identity_helpers import add_users_with_identities


class _SampleError(Coded, Exception):
    code = "SAMPLE_FAILED"


class _SampleValueError(Coded, ValueError):
    code = "SAMPLE_INVALID"


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(CodedHTTPException, coded_http_exception_handler)

    @app.get("/boom")
    async def boom():
        raise exc

    return app


async def _get(exc: Exception):
    transport = ASGITransport(app=_app_raising(exc))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get("/boom")


class TestCodedHandler:
    @pytest.mark.asyncio
    async def test_body_without_params(self):
        response = await _get(CodedHTTPException(503, "AI_DISABLED", "AI is off"))

        assert response.status_code == 503
        assert response.json() == {"detail": "AI is off", "error_code": "AI_DISABLED"}

    @pytest.mark.asyncio
    async def test_params_are_top_level_and_detail_stays_a_string(self):
        response = await _get(CodedHTTPException(413, "IMAGE_TOO_LARGE", "Too big", {"limit": 50}))

        assert response.status_code == 413
        assert response.json() == {
            "detail": "Too big",
            "error_code": "IMAGE_TOO_LARGE",
            "params": {"limit": 50},
        }

    @pytest.mark.asyncio
    async def test_headers_are_kept(self):
        response = await _get(
            CodedHTTPException(
                401, "NOT_AUTHENTICATED", "No", headers={"WWW-Authenticate": "Bearer"}
            )
        )

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_is_an_http_exception(self):
        assert isinstance(CodedHTTPException(404, "X", "y"), HTTPException)


class TestValidationCode:
    @pytest.mark.asyncio
    async def test_request_validation_carries_code_and_field_errors(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            "/api/v1/outfits/suggest", json={"occasion": 5}, headers=auth_headers
        )

        body = response.json()
        assert response.status_code == 422
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["detail"] == "Validation error"
        assert body["errors"]


class TestCoded:
    def test_class_default_code(self):
        error = _SampleError("went wrong")

        assert error.code == "SAMPLE_FAILED"
        assert error.params == {}
        assert str(error) == "went wrong"

    def test_code_and_params_override(self):
        error = _SampleError("too many", code="SAMPLE_LIMIT", limit=3)

        assert error.code == "SAMPLE_LIMIT"
        assert error.params == {"limit": 3}
        assert error.args == ("too many",)

    def test_base_class_is_kept(self):
        assert isinstance(_SampleValueError("bad"), ValueError)
        assert isinstance(CodedValueError("bad", code="X"), ValueError)
        assert not isinstance(_SampleError("bad"), ValueError)

    def test_survives_pickle_as_arq_results_do(self):
        error = pickle.loads(pickle.dumps(_SampleError("went wrong", code="SAMPLE_LIMIT", limit=3)))

        assert str(error) == "went wrong"
        assert error.code == "SAMPLE_LIMIT"
        assert error.params == {"limit": 3}


class TestHttpError:
    def test_coded_exception_keeps_its_code_and_params(self):
        exc = http_error(400, _SampleError("too many", code="SAMPLE_LIMIT", limit=3), "FALLBACK")

        assert exc.status_code == 400
        assert exc.error_code == "SAMPLE_LIMIT"
        assert exc.params == {"limit": 3}
        assert exc.detail == "too many"

    def test_uncoded_exception_takes_the_fallback(self):
        exc = http_error(404, FileNotFoundError("Image not found: /x"), "IMAGE_NOT_FOUND")

        assert exc.error_code == "IMAGE_NOT_FOUND"
        assert exc.params is None
        assert exc.detail == "Image not found: /x"

    def test_headers_pass_through(self):
        exc = http_error(503, _SampleError("down"), "FALLBACK", headers={"Retry-After": "5"})

        assert exc.headers == {"Retry-After": "5"}


def test_main_app_registers_the_coded_handler():
    assert CodedHTTPException in main_app.exception_handlers


def _png(size: tuple[int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (120, 60, 200)).save(buf, format="PNG")
    return buf.getvalue()


async def _item_without_image(db_session, user, **overrides) -> ClothingItem:
    item = ClothingItem(
        user_id=user.id, type="shirt", image_path="", status=ItemStatus.ready, **overrides
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


class TestItemServiceErrors:
    def test_pixel_limit_carries_megapixels_and_limit(self):
        error = ImageTooLargeError(600_000, 100_000)

        assert error.code == "IMAGE_TOO_MANY_PIXELS"
        assert error.params == {"megapixels": 0.6, "limit": 0.1}
        assert isinstance(error, ValueError)

    def test_upload_limit_carries_the_limit(self):
        error = UploadTooLargeError(7)

        assert error.code == "IMAGE_TOO_LARGE"
        assert error.params == {"limit": 7}
        assert str(error) == "File exceeds the 7 MB upload limit"

    def test_tag_vocabulary_error_is_coded_and_a_value_error(self):
        error = TagVocabularyError("pattern 'x' is not one of: solid")

        assert error.code == "INVALID_TAG_VALUE"
        assert isinstance(error, ValueError)

    def test_missing_file_is_coded(self):
        with pytest.raises(ValueError) as caught:
            ImageService().rotate_image("nobody/missing.jpg")

        assert caught.value.code == "IMAGE_FILE_MISSING"


class TestItemEndpointErrors:
    @pytest.mark.asyncio
    async def test_unknown_item(self, client: AsyncClient, auth_headers):
        response = await client.get(f"/api/v1/items/{uuid4()}", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error_code"] == "ITEM_NOT_FOUND"
        assert "params" not in response.json()

    @pytest.mark.asyncio
    async def test_bulk_upload_limit_names_the_limit(self, client: AsyncClient, auth_headers):
        files = [("images", (f"i{n}.jpg", b"\xff\xd8", "image/jpeg")) for n in range(21)]

        response = await client.post("/api/v1/items/bulk", files=files, headers=auth_headers)

        assert response.status_code == 400
        assert response.json()["error_code"] == "BULK_LIMIT_EXCEEDED"
        assert response.json()["params"] == {"limit": 20}

    @pytest.mark.asyncio
    async def test_bulk_action_limit_names_the_limit(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(items_api.settings, "max_bulk_action_count", 2)

        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"item_ids": [str(uuid4()) for _ in range(3)]},
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "BULK_ACTION_LIMIT_EXCEEDED"
        assert response.json()["params"] == {"limit": 2}

    @pytest.mark.asyncio
    async def test_oversize_upload_names_the_byte_limit(self, client: AsyncClient, auth_headers):
        with patch.object(items_api.settings, "max_upload_size_mb", 1):
            response = await client.post(
                "/api/v1/items",
                files={"image": ("big.png", _png((50, 50)) + b"\0" * 1024 * 1024, "image/png")},
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 413
        assert response.json()["error_code"] == "IMAGE_TOO_LARGE"
        assert response.json()["params"] == {"limit": 1}

    @pytest.mark.asyncio
    async def test_pixel_limit_names_both_numbers(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(image_service_module.settings, "max_image_megapixels", 0.1)

        response = await client.post(
            "/api/v1/items",
            files={"image": ("huge.png", _png((800, 800)), "image/png")},
            data={"skip_ai": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "IMAGE_TOO_MANY_PIXELS"
        assert response.json()["params"] == {"megapixels": 0.6, "limit": 0.1}

    @pytest.mark.asyncio
    async def test_not_an_image(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/items",
            files={"image": ("note.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_IMAGE"

    @pytest.mark.asyncio
    async def test_rotate_item_without_image(
        self, client: AsyncClient, auth_headers, test_user, db_session
    ):
        item = await _item_without_image(db_session, test_user)

        response = await client.post(f"/api/v1/items/{item.id}/rotate", headers=auth_headers)

        assert response.status_code == 400
        assert response.json()["error_code"] == "ITEM_HAS_NO_IMAGE"

    @pytest.mark.asyncio
    async def test_restore_without_original(
        self, client: AsyncClient, auth_headers, test_user, db_session
    ):
        item = await _item_without_image(db_session, test_user)

        response = await client.post(
            f"/api/v1/items/{item.id}/restore-original", headers=auth_headers
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "NO_ORIGINAL_IMAGE"

    @pytest.mark.asyncio
    async def test_another_users_item_is_not_found(
        self, client: AsyncClient, auth_headers, db_session
    ):
        other_id = uuid4()
        other = User(
            id=other_id,
            external_id=f"other-{other_id}",
            email=f"other-{other_id}@example.com",
            display_name="Other",
            timezone="UTC",
            is_active=True,
            onboarding_completed=False,
            email_verified=True,
        )
        await add_users_with_identities(db_session, other)
        await db_session.commit()
        item = await _item_without_image(db_session, other)

        response = await client.get(f"/api/v1/items/{item.id}", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error_code"] == "ITEM_NOT_FOUND"


class TestImageEndpointErrors:
    @pytest.mark.asyncio
    async def test_bad_user_id(self, client: AsyncClient):
        response = await client.get("/api/v1/images/not-a-uuid/a.jpg")

        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_IMAGE_PATH"

    @pytest.mark.asyncio
    async def test_unsigned_image_is_denied(self, client: AsyncClient):
        response = await client.get(f"/api/v1/images/{uuid4()}/a.jpg")

        assert response.status_code == 401
        assert response.json()["error_code"] == "ACCESS_DENIED"


class TestOutfitServiceErrors:
    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (InsufficientWardrobeError, "INSUFFICIENT_WARDROBE"),
            (AIRecommendationError, "AI_SERVICE_UNAVAILABLE"),
            (InsufficientItemsError, "INSUFFICIENT_ITEMS_FOR_PAIRING"),
            (AIGenerationError, "AI_SERVICE_UNAVAILABLE"),
            (ItemOwnershipError, "OUTFIT_ITEM_OWNERSHIP"),
            (OutfitWornImmutableError, "OUTFIT_WORN_IMMUTABLE"),
            (OutfitNotTemplateError, "OUTFIT_NOT_TEMPLATE"),
        ],
    )
    def test_service_errors_carry_their_code_and_keep_their_base(self, error, code):
        raised = error("message")

        assert isinstance(raised, Coded)
        assert raised.code == code
        assert not isinstance(raised, ValueError)
        assert http_error(400, raised, "OTHER").error_code == code

    @pytest.mark.asyncio
    async def test_unset_location_is_coded_and_still_a_value_error(self, db_session, test_user):
        test_user.location_lat = None
        test_user.location_lon = None
        test_user.location_name = None

        with pytest.raises(ValueError) as raised:
            await RecommendationService(db_session).generate_recommendation(
                user=test_user, occasion="casual"
            )

        assert raised.value.code == "LOCATION_NOT_SET"

    @pytest.mark.asyncio
    async def test_unresolvable_location_name_is_coded(self, db_session, test_user):
        test_user.location_lat = None
        test_user.location_lon = None
        test_user.location_name = "Nowhere"
        service = RecommendationService(db_session)
        service.weather_service = AsyncMock()
        service.weather_service.geocode_location_name.side_effect = GeocodingServiceError("down")

        with pytest.raises(ValueError) as raised:
            await service.generate_recommendation(user=test_user, occasion="casual")

        assert raised.value.code == "LOCATION_UNRESOLVED"

    @pytest.mark.asyncio
    async def test_weather_failure_is_coded(self, db_session, test_user):
        test_user.location_lat = 10
        test_user.location_lon = 10
        service = RecommendationService(db_session)
        service.weather_service = AsyncMock()
        service.weather_service.get_current_weather.side_effect = WeatherServiceError("down")

        with pytest.raises(ValueError) as raised:
            await service.generate_recommendation(user=test_user, occasion="casual")

        assert raised.value.code == "WEATHER_UNAVAILABLE"


class TestOutfitEndpointErrors:
    @pytest.mark.asyncio
    async def test_unknown_outfit(self, client: AsyncClient, auth_headers):
        response = await client.get(f"/api/v1/outfits/{uuid4()}", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error_code"] == "OUTFIT_NOT_FOUND"
        assert "params" not in response.json()

    @pytest.mark.asyncio
    async def test_family_rating_of_unknown_outfit(self, client: AsyncClient, auth_headers):
        response = await client.get(
            f"/api/v1/outfits/{uuid4()}/family-ratings", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "OUTFIT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_bulk_delete_limit_names_the_limit(self, client: AsyncClient, auth_headers):
        limit = get_settings().max_bulk_action_count

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"outfit_ids": [str(uuid4()) for _ in range(limit + 1)]},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "BULK_ACTION_LIMIT_EXCEEDED"
        assert response.json()["params"] == {"limit": limit}

    @pytest.mark.asyncio
    async def test_empty_patch(self, client: AsyncClient, auth_headers):
        response = await client.patch(f"/api/v1/outfits/{uuid4()}", json={}, headers=auth_headers)

        assert response.status_code == 400
        assert response.json()["error_code"] == "PATCH_EMPTY"

    @pytest.mark.asyncio
    async def test_studio_kill_switch(self, client: AsyncClient, auth_headers, monkeypatch):
        monkeypatch.setattr(get_settings(), "studio_disabled", True, raising=False)

        response = await client.patch(
            f"/api/v1/outfits/{uuid4()}", json={"name": "x"}, headers=auth_headers
        )

        assert response.status_code == 503
        assert response.json()["error_code"] == "STUDIO_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_suggest_without_enough_items_is_coded(self, client: AsyncClient, auth_headers):
        with patch.object(
            RecommendationService,
            "generate_recommendation",
            AsyncMock(side_effect=InsufficientWardrobeError("Not enough items")),
        ):
            response = await client.post(
                "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
            )

        assert response.status_code == 400
        assert response.json()["error_code"] == "INSUFFICIENT_WARDROBE"
        assert response.json()["detail"] == "Not enough items"

    @pytest.mark.asyncio
    async def test_suggest_with_unset_location_keeps_the_service_code(
        self, client: AsyncClient, auth_headers
    ):
        with patch.object(
            RecommendationService,
            "generate_recommendation",
            AsyncMock(side_effect=CodedValueError("No location", code="LOCATION_NOT_SET")),
        ):
            response = await client.post(
                "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
            )

        assert response.status_code == 400
        assert response.json()["error_code"] == "LOCATION_NOT_SET"

    @pytest.mark.asyncio
    async def test_suggest_with_a_failing_ai_is_coded(self, client: AsyncClient, auth_headers):
        with patch.object(
            RecommendationService,
            "generate_recommendation",
            AsyncMock(side_effect=AIRecommendationError("AI service is not available")),
        ):
            response = await client.post(
                "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
            )

        assert response.status_code == 503
        assert response.json()["error_code"] == "AI_SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_plain_value_error_falls_back_to_invalid_input(
        self, client: AsyncClient, auth_headers
    ):
        with patch.object(
            RecommendationService,
            "generate_recommendation",
            AsyncMock(side_effect=ValueError("odd")),
        ):
            response = await client.post(
                "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
            )

        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_INPUT"


class TestPairingEndpointErrors:
    @pytest.mark.asyncio
    async def test_unknown_pairing(self, client: AsyncClient, auth_headers):
        response = await client.delete(f"/api/v1/pairings/{uuid4()}", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error_code"] == "PAIRING_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_generating_for_an_unavailable_source_item(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            f"/api/v1/pairings/generate/{uuid4()}",
            json={"num_pairings": 1},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "SOURCE_ITEM_UNAVAILABLE"
