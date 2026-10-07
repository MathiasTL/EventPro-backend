from app.domain.exceptions.resource_exceptions import DomainError


class EventRoleForbiddenError(DomainError):
    code = "forbidden"


class EventAccessDeniedError(DomainError):
    code = "forbidden"

    def __init__(self) -> None:
        super().__init__("El operador requiere una asignación activa al evento para iniciarlo.")
