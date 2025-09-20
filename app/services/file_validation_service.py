"""Utilities for validating and staging uploaded files before persistence."""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile

from app.config.settings import settings

logger = logging.getLogger(__name__)


class FileValidationError(Exception):
    """Raised when an uploaded file violates guardrail policies."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class FileValidationService:
    """Validate uploads and move them through a temporary staging area."""

    _SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")

    def __init__(
        self,
        *,
        allowed_extensions: Optional[list[str]] = None,
        max_size_mb: Optional[int] = None,
        chunk_size: Optional[int] = None,
        temp_dir: Optional[Path | str] = None,
        storage_dir: Optional[Path | str] = None,
        scan_command: Optional[str] = None,
        scan_timeout: Optional[int] = None,
    ) -> None:
        allowed = allowed_extensions or settings.UPLOAD_ALLOWED_EXTENSIONS
        self._allowed_extensions = {ext.lower().lstrip('.') for ext in allowed}
        resolved_max_size = settings.UPLOAD_MAX_SIZE_MB if max_size_mb is None else max_size_mb
        self._max_bytes = int(max(resolved_max_size, 0) * 1024 * 1024)
        self._chunk_size = int(chunk_size or settings.UPLOAD_CHUNK_SIZE_BYTES)

        resolved_storage_dir = Path(storage_dir or settings.UPLOAD_STORAGE_DIR)
        resolved_storage_dir.mkdir(parents=True, exist_ok=True)
        self._storage_dir = resolved_storage_dir

        default_temp_dir = Path(settings.DATA_DIR) / "tmp_uploads"
        resolved_temp_dir = Path(temp_dir or settings.UPLOAD_TEMP_DIR or default_temp_dir)
        resolved_temp_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir = resolved_temp_dir

        self._scan_command = scan_command or settings.UPLOAD_SCAN_COMMAND
        self._scan_timeout = scan_timeout or settings.UPLOAD_SCAN_TIMEOUT_SECONDS

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def sanitize_filename(self, original_name: str) -> str:
        """Return a filesystem-safe filename preserving the original extension."""

        candidate = Path(original_name or "").name
        if not candidate:
            candidate = "file"

        sanitized = self._SAFE_NAME_PATTERN.sub("_", candidate)
        sanitized = sanitized.strip("._")
        if not sanitized:
            sanitized = "file"

        # Avoid stripping the extension entirely when the filename becomes empty.
        suffix = Path(candidate).suffix
        if suffix and not sanitized.endswith(suffix):
            sanitized += suffix

        return sanitized

    def ensure_extension_allowed(self, filename: str) -> None:
        extension = Path(filename).suffix.lower().lstrip('.')
        if not extension:
            raise FileValidationError("Files must include an extension.", status_code=415)
        if extension not in self._allowed_extensions:
            raise FileValidationError(
                "Unsupported file type. Please upload an allowed format.",
                status_code=415,
            )

    def generate_unique_name(self, filename: str) -> str:
        safe_name = self.sanitize_filename(filename)
        extension = Path(safe_name).suffix
        stem = Path(safe_name).stem
        unique_prefix = uuid4().hex
        return f"{unique_prefix}_{stem}{extension}" if stem else f"{unique_prefix}{extension}"

    def temp_path_for(self, filename: str) -> Path:
        return self._temp_dir / filename

    def final_path_for(self, filename: str) -> Path:
        return self._storage_dir / filename

    def _enforce_size_limit(self, total_bytes: int) -> None:
        if self._max_bytes and total_bytes > self._max_bytes:
            raise FileValidationError(
                f"File exceeds the maximum allowed size of {self._max_bytes // (1024 * 1024)} MB.",
                status_code=413,
            )

    def write_upload_to_temp(self, upload: UploadFile, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            if hasattr(upload.file, "seek"):
                try:
                    upload.file.seek(0)
                except Exception:
                    logger.debug("Upload file object does not support seek reset.")
            with destination.open("wb") as buffer:
                while True:
                    chunk = upload.file.read(self._chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    self._enforce_size_limit(total)
                    buffer.write(chunk)
        except FileValidationError:
            destination.unlink(missing_ok=True)
            raise
        except Exception:
            destination.unlink(missing_ok=True)
            raise FileValidationError("Could not persist uploaded file.", status_code=500)
        return total

    def scan_file(self, path: Path) -> None:
        if not self._scan_command:
            logger.debug("Skipping malware scan for %s; no scan command configured.", path)
            return

        command = [arg.replace("{path}", str(path)) for arg in shlex.split(self._scan_command)]
        if not any(str(path) in arg for arg in command):
            command.append(str(path))

        try:
            logger.debug("Scanning uploaded file with command: %s", command)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._scan_timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            logger.error("Upload scan command is not available: %s", self._scan_command)
            raise FileValidationError("File scanning service is unavailable.", status_code=503) from exc
        except subprocess.TimeoutExpired as exc:
            logger.warning("Upload scan command timed out for %s", path)
            raise FileValidationError("File scan timed out. Please retry later.", status_code=503) from exc

        if result.returncode != 0:
            logger.warning(
                "File scan failed for %s with exit code %s: %s", path, result.returncode, result.stderr
            )
            raise FileValidationError("Uploaded file failed security scanning.", status_code=422)

    def promote_to_permanent_storage(self, temp_path: Path, final_name: str) -> Path:
        destination = self.final_path_for(final_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(destination)
        return destination


_validation_service: Optional[FileValidationService] = None


def get_file_validation_service() -> FileValidationService:
    global _validation_service
    if _validation_service is None:
        _validation_service = FileValidationService()
    return _validation_service

