import os
from pathlib import Path
from typing import Optional
from packages.storage.object_store.base import ObjectStore


class LocalFileObjectStore(ObjectStore):
    def __init__(self, base_dir: str = "./data/storage"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        clean_key = key.lstrip("/")
        return self.base_dir / clean_key

    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return str(path)

    async def get_object(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
        with open(path, "rb") as f:
            return f.read()

    async def delete_object(self, key: str) -> None:
        path = self._resolve_path(key)
        if path.exists():
            os.remove(path)

    async def exists(self, key: str) -> bool:
        return self._resolve_path(key).exists()

    def get_public_url(self, key: str) -> str:
        return f"/api/v1/storage/{key.lstrip('/')}"


class MemoryObjectStore(ObjectStore):
    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._store[key] = data
        return f"memory://{key}"

    async def get_object(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(f"Object not found in memory: {key}")
        return self._store[key]

    async def delete_object(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    def get_public_url(self, key: str) -> str:
        return f"memory://{key}"
