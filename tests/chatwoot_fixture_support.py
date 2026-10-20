"""Carga y saneamiento de los fixtures de Chatwoot usados por las pruebas."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "chatwoot"

# Teléfonos inventados permitidos; cualquier otra secuencia larga de dígitos se rechaza.
ALLOWED_PHONE_DIGITS = frozenset({"51999111222", "51999333444"})
ALLOWED_HOST_SUFFIXES = ("example.org", "example.com", "example.test")
REDACTED = "REDACTED"

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DIGIT_RUN = re.compile(r"\d{9,}")
# Marcas de tiempo Unix (2023-2027): ningún teléfono NANP de 10 dígitos empieza con 1.
_EPOCH_SECONDS = re.compile(r"1[78]\d{8}")
_EMAIL = re.compile(r"[^@\s/]+@[^@\s/]+\.[^@\s/]+")
_URL = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")
_SIGNED_URL_MARKERS = ("x-amz", "signature=", "expires=", "token=", "x-goog", "sig=")
_SECRET_KEY_NAMES = re.compile(r"token|secret|password|authorization|api_key", re.IGNORECASE)
_SIGNATURE_HEADER = "x-chatwoot-signature"
_REQUIRED_KEYS = ("provisional", "headers", "body")


def fixture_names() -> list[str]:
    """Nombres (sin extensión) de los fixtures presentes, ordenados."""

    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(path.stem for path in FIXTURES_DIR.glob("*.json"))


def load_fixture(name: str) -> dict[str, Any]:
    """Lee un fixture completo (`provisional`, `headers`, `body`)."""

    document = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _walk(
    value: Any, path: str = "$", key: str | None = None
) -> Iterator[tuple[str, str | None, Any]]:
    """Recorre el documento entregando (ruta, clave más cercana, valor) de cada nodo."""

    yield path, key, value
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk(child, f"{path}.{child_key}", str(child_key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]", key)


def _string_violations(text: str) -> list[str]:
    """Hallazgos de un texto; devuelve solo categorías, nunca el valor encontrado."""

    findings: list[str] = []
    scrubbed = _UUID.sub("", text)
    for run in _DIGIT_RUN.findall(scrubbed):
        if run not in ALLOWED_PHONE_DIGITS and _EPOCH_SECONDS.fullmatch(run) is None:
            findings.append("digit-run")
    if _EMAIL.search(scrubbed):
        findings.append("email")
    # Un token mezcla letras y dígitos; un código de error en snake_case no tiene dígitos.
    if any(any(c.isdigit() for c in token) for token in _LONG_TOKEN.findall(scrubbed)):
        findings.append("long-token")
    for url in _URL.findall(text):
        host = urlsplit(url).hostname or ""
        if not host.endswith(ALLOWED_HOST_SUFFIXES):
            findings.append("real-host")
        if any(marker in url.lower() for marker in _SIGNED_URL_MARKERS):
            findings.append("signed-url")
    return findings


def scrub_violations(document: Any) -> list[str]:
    """Lista de problemas de saneamiento como `ruta: categoría`; vacía si el fixture es seguro."""

    problems: list[str] = []
    if not isinstance(document, dict):
        return ["$: not-an-object"]
    for key in _REQUIRED_KEYS:
        if key not in document:
            problems.append(f"$.{key}: missing-key")
    if not isinstance(document.get("provisional"), bool):
        problems.append("$.provisional: not-a-bool")
    headers = document.get("headers")
    if isinstance(headers, dict):
        for name, value in headers.items():
            if name.lower() == _SIGNATURE_HEADER and value != REDACTED:
                problems.append(f"$.headers.{name}: real-signature")
    else:
        problems.append("$.headers: not-an-object")
    for path, key, value in _walk(document):
        is_secret_name = key is not None and _SECRET_KEY_NAMES.search(key) is not None
        if is_secret_name and isinstance(value, str) and value not in ("", REDACTED):
            problems.append(f"{path}: secret-key")
        if isinstance(value, str):
            problems.extend(f"{path}: {finding}" for finding in _string_violations(value))
        elif isinstance(value, int) and not isinstance(value, bool) and len(str(value)) >= 11:
            problems.append(f"{path}: numeric-phone")
    return problems
