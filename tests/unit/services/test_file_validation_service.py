from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.services.file_validation_service import (
    FileValidationError,
    FileValidationService,
)


def _make_service(tmp_path: Path, **overrides) -> FileValidationService:
    return FileValidationService(
        allowed_extensions=["txt", "pdf"],
        temp_dir=tmp_path / "tmp",
        storage_dir=tmp_path / "uploads",
        **overrides,
    )


def _make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_sanitize_filename_preserves_extension(tmp_path):
    service = _make_service(tmp_path)
    sanitized = service.sanitize_filename("../my report?.TXT")
    assert sanitized.endswith(".TXT")
    assert ".." not in sanitized


def test_ensure_extension_allowed_blocks_unknown_type(tmp_path):
    service = _make_service(tmp_path)
    with pytest.raises(FileValidationError) as exc:
        service.ensure_extension_allowed("payload.exe")
    assert exc.value.status_code == 415


def test_write_upload_to_temp_enforces_size_limit(tmp_path):
    service = _make_service(tmp_path, max_size_mb=0.00001)
    upload = _make_upload("small.txt", b"0123456789abcdef")

    with pytest.raises(FileValidationError) as exc:
        service.write_upload_to_temp(upload, service.temp_path_for("test.txt"))
    assert exc.value.status_code == 413


def test_promote_moves_file_to_storage(tmp_path):
    service = _make_service(tmp_path)
    upload = _make_upload("doc.txt", b"hello")
    unique_name = service.generate_unique_name(upload.filename)
    temp_path = service.temp_path_for(unique_name)

    written_bytes = service.write_upload_to_temp(upload, temp_path)
    assert written_bytes == 5

    final_path = service.promote_to_permanent_storage(temp_path, unique_name)
    assert final_path.exists()
    assert final_path.read_bytes() == b"hello"


def test_scan_file_raises_when_command_fails(tmp_path):
    service = _make_service(tmp_path, scan_command="false")
    sample_path = service.temp_path_for("failing.txt")
    sample_path.write_bytes(b"test")

    with pytest.raises(FileValidationError) as exc:
        service.scan_file(sample_path)
    assert exc.value.status_code == 422

    # Ensure the file remains for further inspection
    assert sample_path.exists()

