"""DTO genérico de página para los listados paginados."""

from dataclasses import dataclass

from app.domain.exceptions.resource_exceptions import ValidationError

MAX_PAGE_SIZE = 100


def validate_pagination(page: int, page_size: int) -> None:
    """``page`` desde 1 y ``page_size`` de 1 a 100; si no, ``ValidationError``."""

    if page < 1:
        raise ValidationError("La página debe ser mayor o igual que 1.")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValidationError(f"El tamaño de página debe estar entre 1 y {MAX_PAGE_SIZE}.")


@dataclass(frozen=True)
class PageDTO[T]:
    """Página de resultados con los datos de paginación del cuerpo REST."""

    items: tuple[T, ...]
    page: int
    page_size: int
    total: int
