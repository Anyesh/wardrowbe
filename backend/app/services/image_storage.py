from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.config import get_settings


class ImageStorage(ABC):
    @abstractmethod
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def signed_url(self, key: str) -> str | None:
        return None


class LocalImageStorage(ImageStorage):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("Invalid storage key")

        full_path = self.root / key
        resolved = full_path.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid storage key")

        return full_path

    @staticmethod
    def _write_file(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    def _delete_file(path: Path) -> None:
        if path.exists():
            path.unlink()

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path_for(key)
        await asyncio.to_thread(self._write_file, path, data)
        return key

    async def get_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path_for(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        await asyncio.to_thread(self._delete_file, path)


@lru_cache
def get_image_storage() -> ImageStorage:
    get_settings.cache_clear()
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalImageStorage(settings.storage_path)
    if settings.storage_backend == "cloudbase":
        if not settings.cloudbase_storage_bucket:
            raise RuntimeError("CLOUDBASE_STORAGE_BUCKET is required for cloudbase storage")
        from app.services.cloudbase_storage import CloudBaseImageStorage

        return CloudBaseImageStorage(settings.cloudbase_storage_bucket, settings.cloudbase_env_id)
    raise RuntimeError(f"Unsupported STORAGE_BACKEND: {settings.storage_backend}")
