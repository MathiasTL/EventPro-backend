"""Medio de pago que el personal puede elegir: ``UNSPECIFIED`` solo lo asigna el bot."""

from typing import Annotated

from pydantic import AfterValidator

from app.domain.entities.payment import PaymentMethod


def _reject_unspecified(value: PaymentMethod) -> PaymentMethod:
    if value is PaymentMethod.UNSPECIFIED:
        raise ValueError("Elige el medio de pago real; UNSPECIFIED solo lo asigna el bot.")
    return value


StaffPaymentMethod = Annotated[PaymentMethod, AfterValidator(_reject_unspecified)]
