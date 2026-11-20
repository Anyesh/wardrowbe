import pickle
from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api import items as items_api
from app.config import Settings, get_settings
from app.main import app as main_app
from app.main import coded_http_exception_handler
from app.models.family import Family, FamilyInvite, FamilyRole
from app.models.item import ClothingItem, ItemStatus
from app.models.notification import NotificationSettings
from app.models.user import User
from app.services import image_service as image_service_module
from app.services.image_service import ImageService, ImageTooLargeError
from app.services.item_service import TagVocabularyError
from app.services.notification_providers import (
    InvalidSenderError,
    channel_config_failure,
)
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
from app.services.user_service import UserEmailConflictError
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

    @pytest.mark.parametrize(
        "operation",
        [
            lambda svc: svc.rotate_image("nobody/missing.jpg"),
            lambda svc: svc.remove_background("nobody/missing.jpg"),
            lambda svc: svc.crop_to_jpeg("nobody/missing.jpg", 0, 0, 1, 1),
        ],
        ids=["rotate", "remove-background", "crop"],
    )
    def test_missing_file_is_coded_without_its_path(self, operation):
        with pytest.raises(ValueError) as caught:
            operation(ImageService())

        assert caught.value.code == "IMAGE_FILE_MISSING"
        assert str(caught.value) == "Image not found"


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


class TestFamilyEndpointErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("get", "/api/v1/families/me", None),
            ("post", "/api/v1/families/me/leave", None),
        ],
    )
    async def test_without_a_family(self, client: AsyncClient, auth_headers, method, path, body):
        response = await getattr(client, method)(path, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error_code"] == "NOT_IN_ANY_FAMILY"

    @pytest.mark.asyncio
    async def test_creating_a_second_family(self, client: AsyncClient, auth_headers):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)

        response = await client.post("/api/v1/families", json={"name": "Two"}, headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["error_code"] == "ALREADY_IN_FAMILY"

    @pytest.mark.asyncio
    async def test_joining_with_an_unknown_code(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/families/join", json={"invite_code": "ZZZZZZZZ"}, headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "INVALID_INVITE_CODE"

    @pytest.mark.asyncio
    async def test_joining_with_an_unknown_token(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/families/join-by-token", json={"token": "nope"}, headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "INVITE_LINK_INVALID"

    @pytest.mark.asyncio
    async def test_the_only_admin_cannot_leave(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)
        await db_session.refresh(test_user)
        db_session.add(
            User(
                external_id=f"member-{uuid4().hex}",
                email=f"member-{uuid4().hex}@example.com",
                display_name="Member",
                family_id=test_user.family_id,
                role=FamilyRole.member,
            )
        )
        await db_session.commit()

        response = await client.post("/api/v1/families/me/leave", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["error_code"] == "LAST_ADMIN_CANNOT_LEAVE"

    @pytest.mark.asyncio
    async def test_changing_your_own_role(self, client: AsyncClient, test_user, auth_headers):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)

        response = await client.patch(
            f"/api/v1/families/me/members/{test_user.id}",
            json={"role": "member"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "CANNOT_CHANGE_OWN_ROLE"

    @pytest.mark.asyncio
    async def test_removing_yourself(self, client: AsyncClient, test_user, auth_headers):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)

        response = await client.delete(
            f"/api/v1/families/me/members/{test_user.id}", headers=auth_headers
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "CANNOT_REMOVE_SELF"

    @pytest.mark.asyncio
    async def test_unknown_member(self, client: AsyncClient, auth_headers):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)

        response = await client.delete(
            f"/api/v1/families/me/members/{uuid4()}", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "MEMBER_NOT_IN_FAMILY"

    @pytest.mark.asyncio
    async def test_unknown_invite(self, client: AsyncClient, auth_headers):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)

        response = await client.delete(
            f"/api/v1/families/me/invites/{uuid4()}", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "INVITE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_non_admin_is_refused(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        await client.post("/api/v1/families", json={"name": "One"}, headers=auth_headers)
        test_user.role = FamilyRole.member
        await db_session.commit()

        response = await client.post(
            "/api/v1/families/me/invite", json={"email": "g@example.com"}, headers=auth_headers
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "FAMILY_ADMIN_REQUIRED"

    @pytest.mark.asyncio
    async def test_token_for_another_email_and_unverified_email(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        token = f"tok-{uuid4().hex}"
        family = Family(name="Other", created_by=test_user.id, invite_code=uuid4().hex[:8].upper())
        db_session.add(family)
        await db_session.flush()
        invite = FamilyInvite(
            family_id=family.id,
            email="someone-else@example.com",
            token=token,
            invited_by=test_user.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add(invite)
        await db_session.commit()

        response = await client.post(
            "/api/v1/families/join-by-token", json={"token": token}, headers=auth_headers
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "INVITE_EMAIL_MISMATCH"

        invite.email = test_user.email
        test_user.email_verified = False
        await db_session.commit()

        response = await client.post(
            "/api/v1/families/join-by-token", json={"token": token}, headers=auth_headers
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


class TestUserEndpointErrors:
    @pytest.mark.asyncio
    async def test_unsupported_locale(self, client: AsyncClient, auth_headers):
        response = await client.patch(
            "/api/v1/users/me", json={"locale": "xx"}, headers=auth_headers
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "UNSUPPORTED_LOCALE"

    @pytest.mark.asyncio
    async def test_invalid_timezone(self, client: AsyncClient, auth_headers):
        response = await client.patch(
            "/api/v1/users/me", json={"timezone": "Mars/Base"}, headers=auth_headers
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_TIMEZONE"

    @pytest.mark.asyncio
    async def test_non_positive_measurement(self, client: AsyncClient, auth_headers):
        response = await client.patch(
            "/api/v1/users/me", json={"body_measurements": {"chest": 0}}, headers=auth_headers
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_BODY_MEASUREMENT"


class TestPreferenceEndpointErrors:
    @pytest.mark.asyncio
    async def test_ai_endpoint_test_without_url(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/users/me/preferences/test-ai-endpoint", json={}, headers=auth_headers
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "URL_REQUIRED"

    @pytest.mark.asyncio
    async def test_ai_endpoint_test_with_a_non_http_url(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/users/me/preferences/test-ai-endpoint",
            json={"url": "ftp://host"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "URL_SCHEME_UNSUPPORTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("failure", "code", "params"),
        [
            (httpx.ConnectError("refused"), "AI_ENDPOINT_REFUSED", None),
            (httpx.ReadTimeout("slow"), "AI_ENDPOINT_TIMEOUT", None),
            (RuntimeError("boom"), "AI_ENDPOINT_FAILED", None),
        ],
    )
    async def test_ai_endpoint_test_reports_a_code_for_each_failure(
        self, client: AsyncClient, auth_headers, failure, code, params
    ):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=failure)):
            response = await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": "http://localhost:11434/v1"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["error_code"] == code
        assert "params" not in body or body["params"] is None

    @pytest.mark.asyncio
    async def test_ai_endpoint_test_reports_the_http_status(
        self, client: AsyncClient, auth_headers
    ):
        reply = httpx.Response(503, request=httpx.Request("GET", "http://localhost/api/tags"))
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=reply)):
            response = await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": "http://localhost:11434/v1"},
                headers=auth_headers,
            )

        body = response.json()
        assert body["error_code"] == "AI_ENDPOINT_HTTP_ERROR"
        assert body["params"] == {"status": 503}


class TestLearningEndpointErrors:
    @pytest.mark.asyncio
    async def test_unknown_insight(self, client: AsyncClient, auth_headers):
        response = await client.post(
            f"/api/v1/learning/insights/{uuid4()}/acknowledge", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "INSIGHT_NOT_FOUND"


class TestWeatherEndpointErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["/api/v1/weather/current", "/api/v1/weather/forecast"])
    async def test_location_not_set(
        self, client: AsyncClient, test_user, auth_headers, db_session, path
    ):
        test_user.location_name = None
        test_user.location_lat = None
        test_user.location_lon = None
        await db_session.commit()

        response = await client.get(path, headers=auth_headers)

        assert response.status_code == 400
        assert response.json()["error_code"] == "LOCATION_NOT_SET"

    @pytest.mark.asyncio
    async def test_geocoding_failure(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        test_user.location_name = "Nowhere"
        test_user.location_lat = None
        test_user.location_lon = None
        await db_session.commit()

        with patch(
            "app.api.weather.WeatherService.geocode_location_name",
            AsyncMock(side_effect=GeocodingServiceError("down")),
        ):
            response = await client.get("/api/v1/weather/current", headers=auth_headers)

        assert response.status_code == 503
        assert response.json()["error_code"] == "LOCATION_UNRESOLVED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("path", "method"),
        [
            ("/api/v1/weather/current", "get_current_weather"),
            ("/api/v1/weather/forecast", "get_daily_forecast"),
        ],
    )
    async def test_weather_failure(self, client: AsyncClient, auth_headers, path, method):
        with patch(
            f"app.api.weather.WeatherService.{method}",
            AsyncMock(side_effect=WeatherServiceError("down")),
        ):
            response = await client.get(f"{path}?latitude=10&longitude=10", headers=auth_headers)

        assert response.status_code == 503
        assert response.json()["error_code"] == "WEATHER_UNAVAILABLE"

    def test_service_errors_carry_their_default_codes(self):
        assert WeatherServiceError("x").code == "WEATHER_UNAVAILABLE"
        assert GeocodingServiceError("x").code == "LOCATION_UNRESOLVED"


NTFY_CONFIG = {"server": "https://ntfy.sh", "topic": "my-outfits"}


async def _stored_setting(db_session, user, channel="ntfy", config=None) -> NotificationSettings:
    setting = NotificationSettings(
        user_id=user.id, channel=channel, priority=1, config=config or NTFY_CONFIG
    )
    db_session.add(setting)
    await db_session.commit()
    await db_session.refresh(setting)
    return setting


class TestNotificationEndpointErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("channel", "config", "code", "params"),
        [
            ("ntfy", {"server": "ftp://x", "topic": "outfits"}, "NTFY_SERVER_URL_SCHEME", None),
            (
                "ntfy",
                {"server": "https://" + "a" * 500, "topic": "outfits"},
                "NTFY_SERVER_URL_TOO_LONG",
                {"max_length": 500},
            ),
            ("ntfy", {"topic": "ab"}, "NTFY_TOPIC_TOO_SHORT", {"min_length": 3}),
            ("ntfy", {"topic": "bad topic!"}, "NTFY_TOPIC_INVALID_CHARACTERS", None),
            (
                "mattermost",
                {"webhook_url": "http://x/hooks/a"},
                "MATTERMOST_WEBHOOK_NOT_HTTPS",
                None,
            ),
            ("mattermost", {"webhook_url": "https://x/a"}, "MATTERMOST_WEBHOOK_INVALID", None),
            ("expo_push", {"push_token": "abc"}, "EXPO_PUSH_TOKEN_INVALID", None),
            ("email", {"address": "a..b@example.com"}, "INVALID_CHANNEL_CONFIG", None),
            ("email", {"email": "a@example.com"}, "INVALID_CHANNEL_CONFIG", None),
            ("ntfy", {}, "INVALID_CHANNEL_CONFIG", None),
        ],
    )
    async def test_a_bad_channel_config_returns_its_code(
        self, client: AsyncClient, auth_headers, channel, config, code, params
    ):
        response = await client.post(
            "/api/v1/notifications/settings",
            json={"channel": channel, "config": config},
            headers=auth_headers,
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == code
        assert body.get("params") == params

    @pytest.mark.asyncio
    async def test_a_bad_config_update_returns_its_code(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        setting = await _stored_setting(db_session, test_user)

        response = await client.patch(
            f"/api/v1/notifications/settings/{setting.id}",
            json={"config": {"topic": "ab"}},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "NTFY_TOPIC_TOO_SHORT"
        assert response.json()["params"] == {"min_length": 3}

    @pytest.mark.asyncio
    async def test_a_duplicate_channel(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        await _stored_setting(db_session, test_user)

        response = await client.post(
            "/api/v1/notifications/settings",
            json={"channel": "ntfy", "config": NTFY_CONFIG},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "DUPLICATE_CHANNEL"
        assert response.json()["params"] == {"channel": "ntfy"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "suffix", "body"),
        [
            ("GET", "", None),
            ("PATCH", "", {"enabled": False}),
            ("PATCH", "", {"config": NTFY_CONFIG}),
            ("DELETE", "", None),
            ("POST", "/test", None),
        ],
    )
    async def test_a_missing_channel(self, client: AsyncClient, auth_headers, method, suffix, body):
        response = await client.request(
            method,
            f"/api/v1/notifications/settings/{uuid4()}{suffix}",
            json=body,
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "CHANNEL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_a_stored_config_this_version_rejects_cannot_be_tested(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        setting = await _stored_setting(db_session, test_user, config={"topic": "ab"})

        response = await client.post(
            f"/api/v1/notifications/settings/{setting.id}/test", headers=auth_headers
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "NTFY_TOPIC_TOO_SHORT"

    @pytest.mark.asyncio
    async def test_the_channel_response_carries_the_config_error_code(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        setting = await _stored_setting(db_session, test_user, config={"topic": "ab"})
        healthy = await _stored_setting(
            db_session, test_user, "mattermost", {"webhook_url": "https://mm.example.com/hooks/abc"}
        )

        listed = await client.get("/api/v1/notifications/settings", headers=auth_headers)
        single = await client.get(
            f"/api/v1/notifications/settings/{setting.id}", headers=auth_headers
        )

        rows = {row["id"]: row for row in listed.json()}
        assert rows[str(setting.id)]["config_error_code"] == "NTFY_TOPIC_TOO_SHORT"
        assert rows[str(setting.id)]["config_error_params"] == {"min_length": 3}
        assert rows[str(setting.id)]["config_error"].endswith("Topic must be at least 3 characters")
        assert rows[str(healthy.id)]["config_error_code"] is None
        assert rows[str(healthy.id)]["config_error_params"] is None
        assert single.json()["config_error_code"] == "NTFY_TOPIC_TOO_SHORT"

    def test_config_error_code_of_a_plain_value_error_and_a_wrong_shape(self):
        plain = channel_config_failure("email", {"address": "a..b@example.com"})
        wrong_shape = channel_config_failure("email", None)

        assert (plain.code, wrong_shape.code) == (
            "INVALID_CHANNEL_CONFIG",
            "INVALID_CHANNEL_CONFIG",
        )
        assert channel_config_failure("ntfy", NTFY_CONFIG) is None

    @pytest.mark.asyncio
    async def test_an_invalid_push_token(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/notifications/push-token", json={"push_token": "nope"}, headers=auth_headers
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_PUSH_TOKEN"

    @pytest.mark.asyncio
    async def test_a_missing_schedule(self, client: AsyncClient, auth_headers):
        responses = [
            await client.get(f"/api/v1/notifications/schedules/{uuid4()}", headers=auth_headers),
            await client.patch(
                f"/api/v1/notifications/schedules/{uuid4()}",
                json={"enabled": False},
                headers=auth_headers,
            ),
            await client.delete(f"/api/v1/notifications/schedules/{uuid4()}", headers=auth_headers),
        ]

        assert [r.status_code for r in responses] == [404, 404, 404]
        assert {r.json()["error_code"] for r in responses} == {"SCHEDULE_NOT_FOUND"}

    @pytest.mark.asyncio
    async def test_a_duplicate_schedule(self, client: AsyncClient, auth_headers):
        body = {"day_of_week": 1, "notification_time": "08:00", "occasion": "casual"}
        first = await client.post(
            "/api/v1/notifications/schedules", json=body, headers=auth_headers
        )
        second = await client.post(
            "/api/v1/notifications/schedules", json=body, headers=auth_headers
        )

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["error_code"] == "DUPLICATE_SCHEDULE"

    @pytest.mark.asyncio
    async def test_schedule_validators_stay_plain_validation_errors(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            "/api/v1/notifications/schedules",
            json={"day_of_week": 9, "notification_time": "08:00"},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"


class TestNotificationTestSendErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("channel", "config"),
        [
            ("ntfy", NTFY_CONFIG),
            ("mattermost", {"webhook_url": "https://mm.example.com/hooks/abc"}),
            ("expo_push", {"push_token": "ExponentPushToken[abc]"}),
        ],
    )
    async def test_an_http_failure_carries_the_status(
        self, client: AsyncClient, test_user, auth_headers, db_session, channel, config
    ):
        setting = await _stored_setting(db_session, test_user, channel, config)

        with patch(
            "httpx.AsyncClient.post", AsyncMock(return_value=httpx.Response(502, text="bad"))
        ):
            response = await client.request(
                "POST",
                f"/api/v1/notifications/settings/{setting.id}/test",
                headers=auth_headers,
            )

        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "NOTIFICATION_HTTP_ERROR"
        assert body["params"] == {"status": 502}
        assert body["detail"].startswith("HTTP 502")

    @pytest.mark.asyncio
    async def test_a_connection_failure_is_a_generic_coded_error(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        setting = await _stored_setting(db_session, test_user)

        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.ConnectError("down"))):
            response = await client.request(
                "POST",
                f"/api/v1/notifications/settings/{setting.id}/test",
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert response.json()["error_code"] == "NOTIFICATION_TEST_FAILED"
        assert "params" not in response.json()

    @pytest.mark.asyncio
    async def test_email_without_smtp(
        self, client: AsyncClient, test_user, auth_headers, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            "app.services.notification_providers.get_settings",
            lambda: Settings(_env_file=None),
        )
        setting = await _stored_setting(
            db_session, test_user, "email", {"address": "to@example.com"}
        )

        response = await client.request(
            "POST",
            f"/api/v1/notifications/settings/{setting.id}/test",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "SMTP_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_email_with_an_unusable_sender(
        self, client: AsyncClient, test_user, auth_headers, db_session, monkeypatch
    ):
        settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_from_email="a b c")
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
        setting = await _stored_setting(
            db_session, test_user, "email", {"address": "to@example.com"}
        )

        response = await client.request(
            "POST",
            f"/api/v1/notifications/settings/{setting.id}/test",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "EMAIL_SENDER_INVALID"
        assert response.json()["params"] == {"sender": "a b c"}

    @pytest.mark.asyncio
    async def test_a_successful_test_send_stays_a_200(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        setting = await _stored_setting(db_session, test_user)

        with patch(
            "httpx.AsyncClient.post",
            AsyncMock(return_value=httpx.Response(200, json={"id": "x"})),
        ):
            response = await client.request(
                "POST",
                f"/api/v1/notifications/settings/{setting.id}/test",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_the_invalid_sender_error_is_still_a_value_error_with_a_code(self):
        error = InvalidSenderError("x", sender="a b c")

        assert isinstance(error, ValueError)
        assert (error.code, error.params) == ("EMAIL_SENDER_INVALID", {"sender": "a b c"})


PROXY_SECRET = "s" * 32


def _forward_auth_settings(**overrides) -> Settings:
    return get_settings().model_copy(
        update={"debug": False, "forward_auth_secret": PROXY_SECRET, **overrides}
    )


def _proxy_headers(user: str, email: str, secret: str = PROXY_SECRET) -> dict:
    return {
        "X-Forward-Auth-Secret": secret,
        "Remote-User": user,
        "Remote-Email": email,
        "Remote-Name": "Proxy",
    }


class TestAuthEndpointErrors:
    @pytest.mark.asyncio
    async def test_a_request_without_a_token(self, client: AsyncClient):
        response = await client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert response.json()["error_code"] == "NOT_AUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_a_malformed_token(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer not-a-token"}
        )

        assert response.status_code == 401
        assert response.json()["error_code"] == "AUTH_TOKEN_INVALID"
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_a_wrong_forward_auth_secret(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_settings()):
            response = await client.post(
                "/api/v1/auth/sync", headers=_proxy_headers("alice", "a@example.com", "x" * 32)
            )

        assert response.status_code == 401
        assert response.json()["error_code"] == "FORWARD_AUTH_SECRET_INVALID"

    @pytest.mark.asyncio
    async def test_missing_proxy_headers(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_settings()):
            response = await client.post(
                "/api/v1/auth/sync", headers={"X-Forward-Auth-Secret": PROXY_SECRET}
            )

        assert response.status_code == 400
        assert response.json()["error_code"] == "PROXY_HEADERS_MISSING"

    @pytest.mark.asyncio
    async def test_a_repeated_proxy_header_names_the_header(self, client: AsyncClient):
        headers = [
            (b"x-forward-auth-secret", PROXY_SECRET.encode()),
            (b"remote-user", b"alice"),
            (b"remote-user", b"bob"),
            (b"remote-email", b"a@example.com"),
        ]
        with patch("app.api.auth.settings", _forward_auth_settings()):
            response = await client.post("/api/v1/auth/sync", headers=headers)

        assert response.status_code == 400
        assert response.json()["error_code"] == "PROXY_HEADER_REPEATED"
        assert response.json()["params"] == {"header": "Remote-User"}

    @pytest.mark.asyncio
    async def test_a_forward_auth_email_conflict_keeps_the_legacy_detail(
        self, client: AsyncClient, db_session
    ):
        subject = f"alice-{uuid4()}"
        stored = User(
            external_id=subject,
            email=f"other-{uuid4()}@example.com",
            display_name="Stored",
            email_verified=True,
        )
        await add_users_with_identities(db_session, stored)
        await db_session.commit()

        with patch("app.api.auth.settings", _forward_auth_settings()):
            response = await client.post(
                "/api/v1/auth/sync",
                headers=_proxy_headers(subject, f"proxy-{uuid4()}@example.com"),
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "legacy_identity_conflict",
            "error_code": "LEGACY_IDENTITY_CONFLICT",
        }

    @pytest.mark.parametrize(
        ("message", "code"),
        [
            ("Email already in use by another account.", "EMAIL_IN_USE"),
            (
                "Email already associated with another account that is signing in concurrently.",
                "CONCURRENT_SIGN_IN",
            ),
            ("legacy_identity_conflict", "LEGACY_IDENTITY_CONFLICT"),
        ],
    )
    def test_every_sign_in_conflict_has_its_own_code(self, message, code):
        error = UserEmailConflictError(message, code=code)

        assert (str(error), error.code) == (message, code)
        assert isinstance(error, Exception)

    @pytest.mark.asyncio
    async def test_the_rate_limit(self, client: AsyncClient):
        bad = _proxy_headers("alice", "a@example.com", "x" * 32)
        with (
            patch("app.api.auth.settings", _forward_auth_settings()),
            patch(
                "app.utils.rate_limit.get_settings",
                return_value=get_settings().model_copy(update={"trusted_proxy_count": 0}),
            ),
        ):
            responses = [await client.post("/api/v1/auth/sync", headers=bad) for _ in range(11)]

        assert [r.status_code for r in responses] == [401] * 10 + [429]
        assert responses[-1].json() == {
            "detail": "Too many requests. Please try again later.",
            "error_code": "RATE_LIMITED",
        }

    @pytest.mark.asyncio
    async def test_the_rate_limit_keeps_its_headers(self):
        response = await _get(
            CodedHTTPException(429, "RATE_LIMITED", "Slow down", headers={"Retry-After": "30"})
        )

        assert response.headers["retry-after"] == "30"
        assert response.json()["error_code"] == "RATE_LIMITED"
