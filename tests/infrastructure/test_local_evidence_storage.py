import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def test_store_and_open_roundtrip(tmp_path) -> None:
    storage = LocalEvidenceStorage(base_path=tmp_path / "uploads")
    path = await storage.store(
        data=PNG_BYTES, content_type="image/png", original_filename="receipt.png"
    )
    assert path.endswith(".png")
    assert "receipt" not in path
    assert await storage.open(path) == PNG_BYTES


async def test_store_rejects_non_image_content(tmp_path) -> None:
    storage = LocalEvidenceStorage(base_path=tmp_path / "uploads")
    with pytest.raises(ValidationError):
        await storage.store(
            data=b"not an image at all", content_type="text/plain", original_filename="x.txt"
        )


async def test_store_rejects_oversize_file(tmp_path) -> None:
    storage = LocalEvidenceStorage(base_path=tmp_path / "uploads")
    with pytest.raises(ValidationError):
        await storage.store(
            data=b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024),
            content_type="image/png",
            original_filename="big.png",
        )


async def test_open_rejects_path_traversal_and_missing(tmp_path) -> None:
    storage = LocalEvidenceStorage(base_path=tmp_path / "uploads")
    with pytest.raises(ValidationError):
        await storage.open("../secrets/eventpro-signing.p12")
    with pytest.raises(ValidationError):
        await storage.open("evidence/missing.png")


def test_max_bytes_is_five_megabytes(tmp_path) -> None:
    assert LocalEvidenceStorage(base_path=tmp_path).max_bytes() == 5 * 1024 * 1024
