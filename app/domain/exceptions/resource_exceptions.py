"""Excepciones de negocio del dominio.

No dependen de ningún framework: la capa web las traduce a códigos HTTP.
"""

from __future__ import annotations


class DomainError(Exception):
    """Error base de negocio."""

    code = "domain-error"


class ValidationError(DomainError):
    """Una invariante de negocio no se cumple."""

    code = "validation-error"


class DuplicateResourceError(DomainError):
    """Ya existe un recurso con la misma clave natural."""

    code = "duplicate-resource"


class ResourceNotFoundError(DomainError):
    """El recurso solicitado no existe."""

    code = "resource-not-found"


class ResourceInUseError(DomainError):
    """El recurso está en uso y no puede eliminarse físicamente."""

    code = "resource-in-use"


class InvalidServiceCategoryError(ValidationError):
    """La categoría de servicio no es válida para el contexto solicitado."""

    code = "invalid-service-category"
