"""Utility service for interacting with Google Cloud Storage when configured."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Optional, Tuple

from app.config.settings import settings

try:
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover - google-cloud-storage may not be installed locally
    storage = None  # type: ignore

logger = logging.getLogger(__name__)


class CloudStorageService:
    """Thin wrapper around the Google Cloud Storage client with graceful fallbacks."""

    def __init__(self, bucket_name: Optional[str]) -> None:
        self.bucket_name = bucket_name
        self._client: Optional["storage.Client"] = None

    # --- Client helpers -------------------------------------------------
    def _is_enabled(self) -> bool:
        return bool(self.bucket_name and storage is not None)

    def _get_client(self) -> Optional["storage.Client"]:
        if not self._is_enabled():
            return None
        if self._client is None:
            try:
                self._client = storage.Client()  # type: ignore[operator]
            except Exception as exc:  # pragma: no cover - network/auth errors in CI
                logger.warning("Failed to initialise Cloud Storage client: %s", exc)
                self._client = None
        return self._client

    def _get_bucket_and_blob(self, uri: str) -> Optional[Tuple[str, str]]:
        if not uri:
            return None
        if uri.startswith("gs://"):
            without_scheme = uri[5:]
            parts = without_scheme.split("/", 1)
            if len(parts) != 2:
                return None
            return parts[0], parts[1]
        if uri.startswith("https://storage.googleapis.com/"):
            without_prefix = uri[len("https://storage.googleapis.com/") :]
            parts = without_prefix.split("/", 1)
            if len(parts) != 2:
                return None
            return parts[0], parts[1]
        return None

    # --- Public API -----------------------------------------------------
    def is_configured(self) -> bool:
        return self._get_client() is not None

    def upload_file(self, local_path: Path, destination: str) -> Optional[str]:
        client = self._get_client()
        if not client:
            return None
        try:
            bucket = client.bucket(self.bucket_name)  # type: ignore[arg-type]
            blob = bucket.blob(destination)
            blob.upload_from_filename(str(local_path))
            logger.info("Uploaded %s to gs://%s/%s", local_path, self.bucket_name, destination)
            return f"gs://{self.bucket_name}/{destination}"
        except Exception as exc:  # pragma: no cover - external failures
            logger.error("Failed to upload %s to Cloud Storage: %s", local_path, exc, exc_info=True)
            return None

    def ensure_local_copy(self, uri_or_path: str) -> Path:
        """Return a local file path for the given storage reference."""
        candidate = Path(uri_or_path)
        if candidate.exists():
            return candidate

        parsed = self._get_bucket_and_blob(uri_or_path)
        client = self._get_client()
        if not parsed or not client:
            raise FileNotFoundError(f"File not available locally or in configured bucket: {uri_or_path}")

        bucket_name, blob_name = parsed
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="origin-attachment-")
        os.close(tmp_fd)
        tmp = Path(tmp_path)
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.download_to_filename(str(tmp))
            logger.info("Downloaded gs://%s/%s to %s", bucket_name, blob_name, tmp)
            return tmp
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise FileNotFoundError(f"Unable to download {uri_or_path}: {exc}")

    def generate_signed_url(self, uri: str, expires_in: Optional[int] = None) -> Optional[str]:
        client = self._get_client()
        parsed = self._get_bucket_and_blob(uri)
        if not client or not parsed:
            return None

        bucket_name, blob_name = parsed
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            ttl_seconds = expires_in or settings.CLOUD_STORAGE_SIGNED_URL_TTL
            signed_url = blob.generate_signed_url(expiration=timedelta(seconds=ttl_seconds))
            return str(signed_url)
        except Exception as exc:  # pragma: no cover - depends on remote service
            logger.error("Failed to generate signed URL for %s: %s", uri, exc, exc_info=True)
            return None


_cloud_storage_service: Optional[CloudStorageService] = None


def get_cloud_storage_service() -> CloudStorageService:
    global _cloud_storage_service
    if _cloud_storage_service is None:
        bucket_name = settings.CLOUD_STORAGE_BUCKET_NAME
        _cloud_storage_service = CloudStorageService(bucket_name)
    return _cloud_storage_service
