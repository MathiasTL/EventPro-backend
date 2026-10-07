"""Contratos de aplicación para la gestión de usuarios del panel (US-23)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class UserFilters:
    role: Role | None = None
    is_active: bool | None = None
    q: str | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class UserReadDTO:
    id: UUID
    full_name: str
    email: str
    phone: str
    role: Role
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class UserPageDTO:
    items: list[UserReadDTO]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class CreateUserInput:
    full_name: str
    email: str
    phone: str
    role: Role
    password: str


@dataclass(frozen=True)
class UpdateUserInput:
    full_name: str | None = None
    phone: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = None
