import io
from typing import Optional
from packages.storage.object_store.base import ObjectStore


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        endpoint_url: str,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "us-east-1",
    ):
        self.endpoint_url = endpoint_url
        self.bucket_name = bucket_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name

    def _get_client(self):
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
        )

    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        client = self._get_client()
        client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return f"s3://{self.bucket_name}/{key}"

    async def get_object(self, key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    async def delete_object(self, key: str) -> None:
        client = self._get_client()
        client.delete_object(Bucket=self.bucket_name, Key=key)

    async def exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    def get_public_url(self, key: str) -> str:
        return f"{self.endpoint_url}/{self.bucket_name}/{key}"
