"""Transformadores ORM Model → DTO y Model ↔ entidad (capa de persistencia)."""

from __future__ import annotations

from app.application.dtos.payment_dto import PaymentReadDTO
from app.domain.entities.payment import (
    AuditStatus,
    Payment,
    PaymentConcept,
    PaymentMethod,
    ValidationStatus,
)
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.payment_models import PaymentModel


def payment_to_dto(model: PaymentModel) -> PaymentReadDTO:
    """Convierte un pago ORM a DTO de lectura."""

    return PaymentReadDTO(
        payment_id=model.id,
        quote_id=model.quote_id,
        concept=PaymentConcept(model.concept),
        payment_method=PaymentMethod(model.payment_method),
        amount=model.amount,
        validation_status=ValidationStatus(model.validation_status),
        event_id=model.event_id,
        audit_status=AuditStatus(model.audit_status) if model.audit_status else None,
        transaction_reference=model.transaction_reference,
        rejection_reason=model.rejection_reason,
        verified_by_user_id=model.verified_by_user_id,
        registered_by_user_id=model.registered_by_user_id,
        audited_by_user_id=model.audited_by_user_id,
        audited_at=model.audited_at,
        audit_notes=model.audit_notes,
        created_at=model.created_at,
    )


def payment_to_model(payment: Payment) -> PaymentModel:
    """Construye un modelo ORM nuevo a partir de la entidad de dominio."""

    return PaymentModel(
        id=payment.id,
        quote_id=payment.quote_id,
        event_id=payment.event_id,
        concept=payment.concept.value,
        payment_method=payment.payment_method.value,
        amount=payment.amount.amount,
        evidence_path=payment.evidence_path,
        transaction_reference=payment.transaction_reference,
        validation_status=payment.validation_status.value,
        rejection_reason=payment.rejection_reason,
        verified_by_user_id=payment.verified_by_user_id,
        verified_at=payment.verified_at,
        registered_by_user_id=payment.registered_by_user_id,
        audit_status=payment.audit_status.value if payment.audit_status else None,
        audited_by_user_id=payment.audited_by_user_id,
        audited_at=payment.audited_at,
        audit_notes=payment.audit_notes,
        created_at=payment.created_at,
    )


def sync_model(model: PaymentModel, payment: Payment) -> PaymentModel:
    """Actualiza un modelo ORM existente desde la entidad de dominio."""

    model.event_id = payment.event_id
    model.validation_status = payment.validation_status.value
    model.rejection_reason = payment.rejection_reason
    model.verified_by_user_id = payment.verified_by_user_id
    model.verified_at = payment.verified_at
    model.audit_status = payment.audit_status.value if payment.audit_status else None
    model.audited_by_user_id = payment.audited_by_user_id
    model.audited_at = payment.audited_at
    model.audit_notes = payment.audit_notes
    return model


def model_to_entity(model: PaymentModel) -> Payment:
    """Reconstruye la entidad de dominio desde el modelo ORM."""

    return Payment(
        id=model.id,
        quote_id=model.quote_id,
        event_id=model.event_id,
        concept=PaymentConcept(model.concept),
        payment_method=PaymentMethod(model.payment_method),
        amount=Money(model.amount),
        evidence_path=model.evidence_path,
        transaction_reference=model.transaction_reference,
        validation_status=ValidationStatus(model.validation_status),
        rejection_reason=model.rejection_reason,
        verified_by_user_id=model.verified_by_user_id,
        verified_at=model.verified_at,
        registered_by_user_id=model.registered_by_user_id,
        audit_status=AuditStatus(model.audit_status) if model.audit_status else None,
        audited_by_user_id=model.audited_by_user_id,
        audited_at=model.audited_at,
        audit_notes=model.audit_notes,
        created_at=model.created_at,
    )
