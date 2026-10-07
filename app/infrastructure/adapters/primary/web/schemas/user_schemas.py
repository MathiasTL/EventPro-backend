"""Esquemas de la API de usuarios del panel (US-23)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.value_objects.role import Role


class UserReadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    phone: str
    role: Role
    is_active: bool
    created_at: datetime


class UserPageResponse(BaseModel):
    items: list[UserReadResponse]
    page: int
    page_size: int
    total: int


class UserCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=150)
    phone: str = Field(pattern=r"^\+?\d{7,20}$", max_length=20)
    role: Role
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name", "email", "phone")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El campo no puede estar vacío.")
        return cleaned

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("El correo no tiene un formato válido.")
        return value


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^\+?\d{7,20}$", max_length=20)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("full_name", "phone")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El campo no puede estar vacío.")
        return cleaned

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UserUpdateRequest":
        if (
            self.full_name is None
            and self.phone is None
            and self.role is None
            and self.is_active is None
            and self.password is None
        ):
            raise ValueError("Debe indicar al menos un campo a actualizar.")
        return self
