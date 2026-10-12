"""httpx registra cada petición en INFO; la URL de búsqueda de contactos lleva el teléfono."""

import logging
from collections.abc import Iterator

import pytest
import structlog

from app.core.logging import configure_logging


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    # configure_logging cambia la configuración global de structlog y del logger de httpx.
    yield
    structlog.reset_defaults()
    logging.getLogger("httpx").setLevel(logging.NOTSET)


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING"])
def test_httpx_request_lines_are_silenced(level: str) -> None:
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    configure_logging(level)
    assert logging.getLogger("httpx").level == logging.WARNING
