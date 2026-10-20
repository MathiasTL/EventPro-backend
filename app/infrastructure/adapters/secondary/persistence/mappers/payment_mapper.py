"""Conversión explícita entre ORM y agregado Payment; la entidad no importa SQLAlchemy."""

from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel


def payment_to_domain(row: PaymentModel) -> Payment:
    return Payment(
        id=row.id,
        quote_id=row.quote_id,
        event_id=row.event_id,
        concept=PaymentConcept(row.concept),
        payment_method=PaymentMethod(row.payment_method),
        amount=Money(row.amount),
        evidence_path=row.evidence_path,
        transaction_reference=row.transaction_reference,
        validation_status=PaymentValidationStatus(row.validation_status),
        rejection_reason=row.rejection_reason,
        verified_by_user_id=row.verified_by_user_id,
        verified_at=row.verified_at,
        registered_by_user_id=row.registered_by_user_id,
        audit_status=PaymentAuditStatus(row.audit_status) if row.audit_status else None,
        audited_by_user_id=row.audited_by_user_id,
        audited_at=row.audited_at,
        audit_notes=row.audit_notes,
        created_at=row.created_at,
    )


def payment_to_model(entity: Payment) -> PaymentModel:
    return PaymentModel(
        id=entity.id,
        quote_id=entity.quote_id,
        event_id=entity.event_id,
        concept=entity.concept.value,
        payment_method=entity.payment_method.value,
        amount=entity.amount.amount,
        evidence_path=entity.evidence_path,
        transaction_reference=entity.transaction_reference,
        validation_status=entity.validation_status.value,
        rejection_reason=entity.rejection_reason,
        verified_by_user_id=entity.verified_by_user_id,
        verified_at=entity.verified_at,
        registered_by_user_id=entity.registered_by_user_id,
        audit_status=entity.audit_status.value if entity.audit_status else None,
        audited_by_user_id=entity.audited_by_user_id,
        audited_at=entity.audited_at,
        audit_notes=entity.audit_notes,
        created_at=entity.created_at,
    )
