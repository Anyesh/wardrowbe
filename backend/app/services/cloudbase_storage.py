from __future__ import annotations

from app.services.image_storage import ImageStorage


class CloudBaseImageStorage(ImageStorage):
    def __init__(self, bucket: str, env_id: str | None = None):
        self.bucket = bucket
        self.env_id = env_id

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError(
            "CloudBase SDK upload will be implemented with deployment credentials"
        )

    async def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError(
            "CloudBase SDK download will be implemented with deployment credentials"
        )

    async def delete(self, key: str) -> None:
        raise NotImplementedError(
            "CloudBase SDK delete will be implemented with deployment credentials"
        )
