from typing import Protocol, Optional


class ObjectStore(Protocol):
    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        ...

    async def get_object(self, key: str) -> bytes:
        ...

    async def delete_object(self, key: str) -> None:
        ...

    async def exists(self, key: str) -> bool:
        ...

    def get_public_url(self, key: str) -> str:
        ...
