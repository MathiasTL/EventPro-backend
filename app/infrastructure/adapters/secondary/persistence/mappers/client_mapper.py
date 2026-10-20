"""Conversión explícita entre ClientModel y la entidad Client."""

from app.domain.entities.client import Client
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel


def client_to_domain(row: ClientModel) -> Client:
    # parse() normaliza teléfonos heredados ("999999999", "51999999999") al formato canónico.
    return Client(
        id=row.id,
        phone=PhoneNumber.parse(row.phone),
        full_name=row.full_name,
        dni=row.dni,
        ruc=row.ruc,
        created_at=row.created_at,
    )


def client_to_model(entity: Client) -> ClientModel:
    return ClientModel(
        id=entity.id,
        phone=entity.phone.value,
        full_name=entity.full_name,
        dni=entity.dni,
        ruc=entity.ruc,
        created_at=entity.created_at,
    )
