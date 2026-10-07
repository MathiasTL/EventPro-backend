"""Gestión de elencos y vinculación con usuarios operadores (RF-29, US-26)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.application.dtos.catalog_dto import CrewDTO
from app.application.ports.output.catalog_admin_port import ICrewAdminPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.domain.entities.catalog import Crew
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.domain.value_objects.service_category import ServiceCategory


class ManageCrewsUseCase:
    """Alta, edición y vinculación de elencos freelance."""

    def __init__(self, crews: ICrewAdminPort, users: IUserRepositoryPort) -> None:
        self._crews = crews
        self._users = users

    async def list_crews(self, *, include_inactive: bool = False) -> Sequence[CrewDTO]:
        return await self._crews.list_crews(include_inactive=include_inactive)

    async def get_crew(self, crew_id: UUID) -> CrewDTO:
        crew = await self._crews.get_crew(crew_id)
        if crew is None:
            raise ResourceNotFoundError("Elenco no encontrado")
        return crew

    async def create_crew(
        self,
        *,
        leader_name: str,
        phone: str,
        service_category: ServiceCategory,
        user_id: UUID | None = None,
    ) -> CrewDTO:
        await self._ensure_user_can_be_linked(user_id, crew_id=None)
        crew = Crew(
            leader_name=leader_name,
            phone=phone,
            service_category=service_category,
            user_id=user_id,
        )
        return await self._crews.create_crew(crew)

    async def update_crew(
        self,
        crew_id: UUID,
        *,
        leader_name: str,
        phone: str,
        service_category: ServiceCategory,
        user_id: UUID | None = None,
        is_active: bool = True,
    ) -> CrewDTO:
        await self._ensure_user_can_be_linked(user_id, crew_id=crew_id)
        crew = Crew(
            leader_name=leader_name,
            phone=phone,
            service_category=service_category,
            user_id=user_id,
            is_active=is_active,
            id=crew_id,
        )
        return await self._crews.update_crew(crew)

    async def _ensure_user_can_be_linked(
        self, user_id: UUID | None, *, crew_id: UUID | None
    ) -> None:
        """US-26: solo un usuario ``OPERADOR`` no vinculado a otro elenco."""

        if user_id is None:
            return
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("Usuario no encontrado")
        if user.role is not Role.OPERADOR:
            raise ValidationError("Solo un usuario con rol OPERADOR puede vincularse a un elenco")
        linked = await self._crews.find_crew_by_user(user_id)
        if linked is not None and linked.id != crew_id:
            raise DuplicateResourceError("El usuario ya está vinculado a otro elenco")
