from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


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

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def get_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()
