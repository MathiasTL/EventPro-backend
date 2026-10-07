"""Conversión de la entidad User a DTO de aplicación."""

from app.application.dtos.user_dto import UserReadDTO
from app.domain.entities.user import User


def to_user_dto(user: User) -> UserReadDTO:
    return UserReadDTO(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )
