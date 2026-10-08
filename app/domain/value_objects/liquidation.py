"""Objetos de valor de la liquidación: cargo de extra y resultado inmutable."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money


def _require_pen(amount: Money, name: str) -> None:
    if not isinstance(amount, Money) or amount.currency != "PEN":
        raise ValidationError(f"{name} debe ser un importe PEN")


@dataclass(frozen=True)
class ExtraCharge:
    """Extra contratado: precio unitario (puede ser cero) y cantidad positiva."""

    unit_price: Money
    quantity: int

    def __post_init__(self) -> None:
        _require_pen(self.unit_price, "unit_price")
        if self.unit_price.amount < 0:
            raise ValidationError("El precio de un extra no puede ser negativo")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValidationError("quantity debe ser un entero")
        if self.quantity <= 0:
            raise ValidationError("La cantidad de un extra debe ser mayor que cero")

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Liquidation:
    """Resultado de ``FinancialEngine.liquidate``.

    Las liquidaciones producidas por ``FinancialEngine`` cumplen que ``balance_services`` +
    ``balance_mobility`` suman ``pending_balance`` (RN-02). Esa igualdad no se valida aquí: las
    filas cargadas desde el flujo manual (PR #22) pueden no cumplirla y se conservan tal como
    fueron almacenadas.
    """

    services_subtotal: Money
    mobility_amount: Money
    total_amount: Money
    advance_amount: Money
    pending_balance: Money
    balance_services: Money
    balance_mobility: Money

    def __post_init__(self) -> None:
        for name in (
            "services_subtotal",
            "mobility_amount",
            "total_amount",
            "advance_amount",
            "pending_balance",
            "balance_services",
            "balance_mobility",
        ):
            _require_pen(getattr(self, name), name)
            if getattr(self, name).amount < 0:
                raise ValidationError(f"{name} no puede ser negativo")
