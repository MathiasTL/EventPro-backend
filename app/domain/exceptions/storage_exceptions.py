"""Errores neutrales de comprobantes, compartidos por todos los módulos."""

from app.domain.exceptions.resource_exceptions import ValidationError


class EvidenceValidationError(ValidationError):
    code = "invalid-file"
