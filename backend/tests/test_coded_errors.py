import pickle

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app as main_app
from app.main import coded_http_exception_handler
from app.utils.errors import Coded, CodedHTTPException, CodedValueError, http_error


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
