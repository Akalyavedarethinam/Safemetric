"""
File storage abstraction.

  local  - files under UPLOAD_DIR (development / single VM)
  s3     - any S3-compatible object store: AWS S3, Cloudflare R2, Supabase Storage,
           Google Cloud Storage (S3 interoperability), MinIO.  Uses boto3.
  azure  - Azure Blob Storage.  Uses azure-storage-blob.

Only storage *keys* are written to the database. Keys are generated server-side
(uuid based) so user-supplied filenames can never cause path traversal.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from . import config

log = logging.getLogger("safemetric.storage")


class StorageError(RuntimeError):
    pass


class LocalStorage:
    name = "local"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise StorageError("Invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise StorageError("File not found in storage")
        return p.read_bytes()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except StorageError:
            pass


class S3Storage:
    name = "s3"

    def __init__(self):
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise StorageError("STORAGE_BACKEND=s3 requires `pip install boto3`") from exc
        if not config.S3_BUCKET:
            raise StorageError("S3_BUCKET is not configured")
        self.bucket = config.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=config.S3_ENDPOINT_URL,
            region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=config.S3_SECRET_ACCESS_KEY or None,
        )

    def put(self, key, data, content_type="application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key):
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:  # pragma: no cover
            raise StorageError(f"Could not read object: {exc}") from exc

    def delete(self, key):
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:  # pragma: no cover
            log.warning("could not delete %s", key)


class AzureStorage:
    name = "azure"

    def __init__(self):
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise StorageError("STORAGE_BACKEND=azure requires `pip install azure-storage-blob`") from exc
        if not config.AZURE_CONNECTION_STRING:
            raise StorageError("AZURE_STORAGE_CONNECTION_STRING is not configured")
        svc = BlobServiceClient.from_connection_string(config.AZURE_CONNECTION_STRING)
        self.container = svc.get_container_client(config.AZURE_CONTAINER)
        try:
            self.container.create_container()
        except Exception:
            pass

    def put(self, key, data, content_type="application/octet-stream"):
        from azure.storage.blob import ContentSettings  # type: ignore
        self.container.upload_blob(key, data, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        return key

    def get(self, key):
        try:
            return self.container.download_blob(key).readall()
        except Exception as exc:  # pragma: no cover
            raise StorageError(f"Could not read blob: {exc}") from exc

    def delete(self, key):
        try:
            self.container.delete_blob(key)
        except Exception:  # pragma: no cover
            pass


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        if config.STORAGE_BACKEND == "s3":
            _storage = S3Storage()
        elif config.STORAGE_BACKEND == "azure":
            _storage = AzureStorage()
        else:
            _storage = LocalStorage(config.UPLOAD_DIR)
        log.info("storage backend: %s", _storage.name)
    return _storage


def new_key(prefix: str, ext: str) -> str:
    ext = ext.lower() if ext.startswith(".") else "." + ext.lower()
    return f"{prefix}/{uuid.uuid4().hex}{ext}"
