from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.domain.exceptions.resource_exceptions import ValidationError
from app.infrastructure.adapters.secondary.storage.document_source_adapter import (
    StorageDocumentSource,
)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _factory() -> MagicMock:
    """Fábrica de sesiones que nunca debería tocarse para rutas del disco local."""

    return MagicMock()


async def test_reads_a_legacy_path_from_the_local_storage(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "contrato.pdf").write_bytes(b"%PDF-1.4 local")

    data = await StorageDocumentSource(_factory()).read("evidence/contrato.pdf")

    assert data == b"%PDF-1.4 local"


async def test_a_missing_local_file_raises_a_domain_error() -> None:
    with pytest.raises(ValidationError):
        await StorageDocumentSource(_factory()).read("evidence/no-existe.pdf")


async def test_rejects_paths_that_escape_the_storage_directory() -> None:
    with pytest.raises(ValidationError):
        await StorageDocumentSource(_factory()).read("../secreto.pdf")
