"""Entidad Client: identidad comercial del cliente de WhatsApp (US-25)."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.phone_number import PhoneNumber

_DNI = re.compile(r"[0-9]{8}")
_RUC = re.compile(r"[0-9]{11}")
_FULL_NAME_MAX = 120


@dataclass(kw_only=True)
class Client:
    phone: PhoneNumber
    full_name: str
    dni: str | None = None
    ruc: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.phone, PhoneNumber):
            raise ValidationError("phone debe ser un PhoneNumber")
        if not isinstance(self.full_name, str) or not self.full_name.strip():
            raise ValidationError("full_name no puede estar vacío")
        self.full_name = self.full_name.strip()
        if len(self.full_name) > _FULL_NAME_MAX:
            raise ValidationError("full_name no puede superar 120 caracteres")
        if self.dni is not None and _DNI.fullmatch(self.dni) is None:
            raise ValidationError("dni debe tener exactamente 8 dígitos")
        if self.ruc is not None and _RUC.fullmatch(self.ruc) is None:
            raise ValidationError("ruc debe tener exactamente 11 dígitos")
