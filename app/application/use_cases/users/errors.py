"""Errores propios del módulo de usuarios (US-23)."""

from app.domain.exceptions.resource_exceptions import DomainError


class SelfModificationError(DomainError):
    """Un SUPERADMIN no puede desactivarse ni degradar su propio rol."""

    code = "self-modification-forbidden"
