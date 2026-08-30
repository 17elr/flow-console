from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image


MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 50_000_000
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class AssetValidationError(ValueError):
    pass


def validate_image(content: bytes) -> dict:
    if not content or len(content) > MAX_BYTES:
        raise AssetValidationError("图片必须非空且不超过 20MB")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            image_format = image.format or ""
    except Exception as exc:
        raise AssetValidationError("文件不是有效图片") from exc
    if image_format not in ALLOWED_FORMATS:
        raise AssetValidationError("仅支持 PNG、JPEG 和 WebP")
    if width * height > MAX_PIXELS:
        raise AssetValidationError("图片像素不能超过 50MP")
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "mime_type": ALLOWED_FORMATS[image_format],
        "width": width,
        "height": height,
        "byte_size": len(content),
        "extension": {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[image_format],
    }


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AssetValidationError("素材链接必须使用 http 或 https")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AssetValidationError("素材域名无法解析") from exc
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise AssetValidationError("禁止访问本机或私网素材地址")


def download_external(url: str) -> bytes:
    _validate_public_url(url)
    with httpx.Client(follow_redirects=False, timeout=20.0) as client:
        current = url
        for _ in range(4):
            _validate_public_url(current)
            with client.stream("GET", current, headers={"User-Agent": "CommerceAssetMirror/1.0"}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise AssetValidationError("素材重定向缺少目标地址")
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                length = int(response.headers.get("content-length", "0") or 0)
                if length > MAX_BYTES:
                    raise AssetValidationError("远程图片超过 20MB")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise AssetValidationError("远程图片超过 20MB")
                    chunks.append(chunk)
                return b"".join(chunks)
        raise AssetValidationError("素材重定向次数过多")


class StorageBackend:
    def put(self, key: str, content: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self) -> None:
        self.root = Path(os.getenv("LOCAL_ASSET_ROOT", Path(__file__).resolve().parents[1] / "data" / "assets"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root.resolve() not in resolved.parents:
            raise AssetValidationError("非法存储路径")
        return resolved

    def put(self, key: str, content: bytes, content_type: str) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, key: str) -> bytes:
        target = self._path(key)
        if not target.exists():
            raise FileNotFoundError(key)
        return target.read_bytes()


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = os.environ["S3_BUCKET"]
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
            config=Config(s3={"addressing_style": "virtual"}),
        )

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


class ResilientS3Storage(StorageBackend):
    """Mirror assets locally so an object-store outage cannot break local work."""

    def __init__(self) -> None:
        self.remote = S3Storage()
        self.local = LocalStorage()

    def put(self, key: str, content: bytes, content_type: str) -> None:
        # The local copy is authoritative for the desktop workflow. Remote upload is
        # best effort and can be retried after billing/network access is restored.
        self.local.put(key, content, content_type)
        try:
            self.remote.put(key, content, content_type)
        except Exception:
            pass

    def get(self, key: str) -> bytes:
        try:
            return self.remote.get(key)
        except Exception:
            return self.local.get(key)


def configured_storage() -> StorageBackend:
    return ResilientS3Storage() if os.getenv("STORAGE_BACKEND", "local").lower() == "s3" else LocalStorage()
