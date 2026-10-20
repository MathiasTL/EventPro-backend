"""Objeto de valor ``PhoneNumber``: teléfono normalizado a E.164 (por defecto Perú, ``+51``).

Es la única fuente de la regla de normalización de teléfonos del sistema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.exceptions.resource_exceptions import ValidationError

_SEPARATORS = re.compile(r"[ \-]")
_RAW_PATTERN = re.compile(r"\+?[0-9]{9,15}")
_CANONICAL_PATTERN = re.compile(r"\+[1-9][0-9]{9,14}")
_PERU_CODE = "51"
_INTERNATIONAL_PREFIX = "00"


@dataclass(frozen=True)
class PhoneNumber:
    """Teléfono en formato canónico ``+<código><número>`` (10 a 15 dígitos)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _CANONICAL_PATTERN.fullmatch(self.value) is None:
            raise ValidationError("El teléfono debe tener formato E.164, por ejemplo +51999999999")

    @classmethod
    def parse(cls, raw: str) -> PhoneNumber:
        """Normaliza ``999999999``, ``51999999999`` y ``+51999999999`` a ``+51999999999``.

        Descarta espacios y guiones (``"+51 999-999-999"``). Nueve dígitos se interpretan
        como número peruano; un número con otro código de país se conserva tal cual.
        Sin ``+``, el prefijo ``00`` es el prefijo internacional: se descarta y el resto
        debe tener entre 10 y 15 dígitos (``"0051999999999"`` da ``+51999999999``).
        """

        if not isinstance(raw, str):
            raise ValidationError("El teléfono debe ser texto")
        cleaned = _SEPARATORS.sub("", raw.strip())
        if _RAW_PATTERN.fullmatch(cleaned) is None:
            raise ValidationError("El teléfono debe tener entre 9 y 15 dígitos, con + opcional")
        digits = cleaned.removeprefix("+")
        if not cleaned.startswith("+") and digits.startswith(_INTERNATIONAL_PREFIX):
            digits = digits.removeprefix(_INTERNATIONAL_PREFIX)
            if not 10 <= len(digits) <= 15:
                raise ValidationError(
                    "Con el prefijo 00 el teléfono debe tener entre 10 y 15 dígitos"
                )
        elif len(digits) == 9:
            digits = _PERU_CODE + digits
        return cls(f"+{digits}")

    @property
    def digits(self) -> str:
        """Dígitos sin el signo ``+`` (``51999999999``)."""

        return self.value.removeprefix("+")

    @property
    def national(self) -> str:
        """Número sin el prefijo ``+51`` cuando es peruano; si no, el valor completo."""

        return self.value.removeprefix(f"+{_PERU_CODE}")

    def __str__(self) -> str:
        return self.value
