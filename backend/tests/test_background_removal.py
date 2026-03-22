from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services.background_removal import (
    BackgroundRemovalProvider,
    HttpProvider,
    RembgProvider,
    get_provider,
)


def _make_rgba_image(w=100, h=100):
    return Image.new("RGBA", (w, h), (255, 0, 0, 128))


def _make_rgb_image(w=100, h=100):
    return Image.new("RGB", (w, h), (200, 150, 100))


class TestRembgProvider:
    def test_remove_calls_rembg(self):
        provider = RembgProvider(model="u2net")
        mock_result = _make_rgba_image()
        mock_new_session = MagicMock(return_value="fake-session")
        mock_remove = MagicMock(return_value=mock_result)
        with (
            patch.dict(
                "sys.modules",
                {"rembg": MagicMock(new_session=mock_new_session, remove=mock_remove)},
            ),
        ):
            result = provider.remove(_make_rgb_image())

        mock_new_session.assert_called_once_with("u2net")
        mock_remove.assert_called_once()
        assert result.mode == "RGBA"

    def test_session_is_cached(self):
        provider = RembgProvider(model="u2net")
        mock_result = _make_rgba_image()
        mock_new_session = MagicMock(return_value="fake-session")
        mock_remove = MagicMock(return_value=mock_result)
        with (
            patch.dict(
                "sys.modules",
                {"rembg": MagicMock(new_session=mock_new_session, remove=mock_remove)},
            ),
        ):
            provider.remove(_make_rgb_image())
            provider.remove(_make_rgb_image())

        mock_new_session.assert_called_once()

    def test_custom_model(self):
        provider = RembgProvider(model="isnet-general-use")
        mock_result = _make_rgba_image()
        mock_new_session = MagicMock(return_value="fake-session")
        mock_remove = MagicMock(return_value=mock_result)
        with (
            patch.dict(
                "sys.modules",
                {"rembg": MagicMock(new_session=mock_new_session, remove=mock_remove)},
            ),
        ):
            provider.remove(_make_rgb_image())

        mock_new_session.assert_called_once_with("isnet-general-use")


class TestHttpProvider:
    def test_remove_posts_to_url(self):
        provider = HttpProvider(url="http://bg-service:5000", api_key="test-key")
        png_bytes = BytesIO()
        _make_rgba_image().save(png_bytes, format="PNG")
        png_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = png_bytes.getvalue()
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.background_removal.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.remove(_make_rgb_image())

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "http://bg-service:5000/api/remove-background" in call_kwargs.args
        assert result.mode == "RGBA"

    def test_strips_trailing_slash(self):
        provider = HttpProvider(url="http://bg-service:5000/")
        assert provider.url == "http://bg-service:5000"

    def test_auth_header_when_api_key_set(self):
        provider = HttpProvider(url="http://bg-service:5000", api_key="my-key")
        png_bytes = BytesIO()
        _make_rgba_image().save(png_bytes, format="PNG")

        mock_response = MagicMock()
        mock_response.content = png_bytes.getvalue()
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.background_removal.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            provider.remove(_make_rgb_image())

        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-key"


class TestGetProvider:
    def setup_method(self):
        import app.services.background_removal as mod

        mod._provider = None

    def test_rembg_provider(self):
        settings = MagicMock()
        settings.bg_removal_provider = "rembg"
        settings.bg_removal_model = "u2net"
        with patch("app.services.background_removal.get_settings", return_value=settings):
            provider = get_provider()
        assert isinstance(provider, RembgProvider)
        assert provider.model == "u2net"

    def test_http_provider(self):
        settings = MagicMock()
        settings.bg_removal_provider = "http"
        settings.bg_removal_url = "http://withoutbg:5000"
        settings.bg_removal_api_key = "key123"
        with patch("app.services.background_removal.get_settings", return_value=settings):
            provider = get_provider()
        assert isinstance(provider, HttpProvider)
        assert provider.url == "http://withoutbg:5000"
        assert provider.api_key == "key123"

    def test_http_provider_requires_url(self):
        settings = MagicMock()
        settings.bg_removal_provider = "http"
        settings.bg_removal_url = None
        with (
            patch("app.services.background_removal.get_settings", return_value=settings),
            pytest.raises(ValueError, match="BG_REMOVAL_URL is required"),
        ):
            get_provider()

    def test_unknown_provider_raises(self):
        settings = MagicMock()
        settings.bg_removal_provider = "magic"
        with (
            patch("app.services.background_removal.get_settings", return_value=settings),
            pytest.raises(ValueError, match="Unknown BG_REMOVAL_PROVIDER"),
        ):
            get_provider()

    def test_provider_is_cached(self):
        settings = MagicMock()
        settings.bg_removal_provider = "rembg"
        settings.bg_removal_model = "u2net"
        with patch("app.services.background_removal.get_settings", return_value=settings):
            p1 = get_provider()
            p2 = get_provider()
        assert p1 is p2

    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BackgroundRemovalProvider()
