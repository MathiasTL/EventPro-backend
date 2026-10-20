import asyncio
import threading
from pathlib import Path

import pytest

from app.domain.exceptions.storage_exceptions import EvidenceValidationError
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from tests.extension_support import PNG_BYTES


async def test_disk_write_runs_in_thread_and_does_not_block_event_loop(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = Path.write_bytes

    def blocked_write(path, data):
        entered.set()
        assert release.wait(3)
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", blocked_write)
    task = asyncio.create_task(
        LocalEvidenceStorage(tmp_path).store(
            data=PNG_BYTES, content_type="image/png", original_filename="x.png"
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.2)
    finally:
        release.set()
        await task


async def test_shared_storage_error_is_neutral_and_keeps_payment_formats(tmp_path):
    with pytest.raises(EvidenceValidationError, match="JPEG, PNG, WebP o PDF"):
        await LocalEvidenceStorage(tmp_path).store(
            data=b"invalid", content_type="image/png", original_filename="x.png"
        )


async def test_cancelled_threaded_store_removes_file_after_writer_finishes(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = Path.write_bytes

    def blocked_write(path, data):
        entered.set()
        assert release.wait(3)
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", blocked_write)
    storage = LocalEvidenceStorage(tmp_path)
    task = asyncio.create_task(
        storage.store(data=PNG_BYTES, content_type="image/png", original_filename="x")
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list((tmp_path / "evidence").iterdir()) == []


async def test_pdf_is_allowed_only_for_payment_storage(tmp_path):
    data = b"%PDF-1.4\n1234"
    storage = LocalEvidenceStorage(tmp_path)
    path = await storage.store(data=data, content_type="image/png", original_filename="fake.png")
    assert path.endswith(".pdf")
    assert await storage.open(path) == data
    await storage.delete(path)
    with pytest.raises(EvidenceValidationError, match="JPEG, PNG o WebP"):
        await LocalEvidenceStorage(
            tmp_path, allowed_mime={"image/jpeg", "image/png", "image/webp"}
        ).store(data=data, content_type="application/pdf", original_filename="x.pdf")
