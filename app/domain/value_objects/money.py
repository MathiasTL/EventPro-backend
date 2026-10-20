"""Objeto de valor ``Money``: importe monetario exacto en una moneda dada.

Usa ``Decimal`` para evitar los errores de coma flotante en los cálculos de dinero,
tal como exige el diccionario de datos (``NUMERIC(10,2)``). Es inmutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    """Importe monetario exacto, redondeado a dos decimales."""

    amount: Decimal
    currency: str = "PEN"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount debe ser un Decimal")
        if not self.currency:
            raise ValueError("Money.currency no puede estar vacío")
        object.__setattr__(self, "amount", self.amount.quantize(_CENT, rounding=ROUND_HALF_UP))

    @classmethod
    def zero(cls, currency: str = "PEN") -> Money:
        """Devuelve un importe cero en la moneda indicada."""

        return cls(Decimal("0.00"), currency)

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"No se pueden combinar monedas distintas: {self.currency} y {other.currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> Money:
        return Money(self.amount * Decimal(factor), self.currency)

    def __rmul__(self, factor: Decimal | int) -> Money:
        return self.__mul__(factor)

    def __lt__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        """Indica si el importe es cero."""

        return self.amount == Decimal("0.00")
