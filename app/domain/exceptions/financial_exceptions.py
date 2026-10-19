from app.domain.exceptions.resource_exceptions import DomainError


class FinancialDataInconsistentError(DomainError):
    """Impide publicar resultados financieros incompletos o inválidos."""

    code = "financial-data-inconsistent"
