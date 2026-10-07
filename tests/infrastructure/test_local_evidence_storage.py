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


async def test_extension_storage_rejects_pdf_by_content_but_payments_still_allow_it(tmp_path):
    pdf = b"%PDF-1.4\n" + b"0" * 64
    general = LocalEvidenceStorage(base_path=tmp_path)
    path = await general.store(data=pdf, content_type="image/png", original_filename="fake.png")
    assert path.endswith(".pdf")
    images = LocalEvidenceStorage(
        base_path=tmp_path, allowed_mime={"image/jpeg", "image/png", "image/webp"}
    )
    with pytest.raises(ValidationError):
        await images.store(data=pdf, content_type="image/png", original_filename="fake.png")
    assert await general.open(path) == pdf


async def test_delete_is_scoped_and_idempotent(tmp_path):
    storage = LocalEvidenceStorage(base_path=tmp_path)
    path = await storage.store(data=PNG_BYTES, content_type="image/png", original_filename="x")
    await storage.delete(path)
    await storage.delete(path)
    with pytest.raises(ValidationError):
        await storage.open(path)
    outside = tmp_path.parent / "outside-us18.txt"
    with pytest.raises(ValidationError):
        await storage.delete("../outside-us18.txt")
    with pytest.raises(ValidationError):
        await storage.delete(str(outside.resolve()))
