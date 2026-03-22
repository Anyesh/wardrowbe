import logging
from abc import ABC, abstractmethod
from io import BytesIO

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)


class BackgroundRemovalProvider(ABC):
    @abstractmethod
    def remove(self, image: Image.Image) -> Image.Image:
        """Remove background from image. Returns RGBA image with transparent background."""


class RembgProvider(BackgroundRemovalProvider):
    def __init__(self, model: str = "u2net"):
        self.model = model
        self._session = None

    def _get_session(self):
        if self._session is None:
            from rembg import new_session

            self._session = new_session(self.model)
        return self._session

    def remove(self, image: Image.Image) -> Image.Image:
        from rembg import remove

        return remove(image, session=self._get_session())


class HttpProvider(BackgroundRemovalProvider):
    def __init__(self, url: str, api_key: str | None = None):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def remove(self, image: Image.Image) -> Image.Image:
        buf = BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.post(
                f"{self.url}/api/remove-background",
                files={"file": ("image.png", buf, "image/png")},
                headers=headers,
            )
            response.raise_for_status()

        return Image.open(BytesIO(response.content)).convert("RGBA")


_provider: BackgroundRemovalProvider | None = None


def get_provider() -> BackgroundRemovalProvider:
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    provider_type = settings.bg_removal_provider

    if provider_type == "rembg":
        _provider = RembgProvider(model=settings.bg_removal_model)
    elif provider_type == "http":
        if not settings.bg_removal_url:
            raise ValueError("BG_REMOVAL_URL is required when BG_REMOVAL_PROVIDER=http")
        _provider = HttpProvider(url=settings.bg_removal_url, api_key=settings.bg_removal_api_key)
    else:
        raise ValueError(f"Unknown BG_REMOVAL_PROVIDER: {provider_type}. Use 'rembg' or 'http'.")

    return _provider
