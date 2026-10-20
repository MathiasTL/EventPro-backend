"""Fixtures compartidas de toda la suite."""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ninguna prueba usa la clave real de ``.env``: el agente de OpenAI queda desactivado.

    Las pruebas del agente usan un modelo con guion y nunca llegan a la red.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "")
    yield
