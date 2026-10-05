"""Datos semilla idempotentes (Docs/03-datos/03-estrategia-migraciones-y-seeds.md).

Uso: python -m app.infrastructure.adapters.secondary.persistence.seed
"""

import asyncio
from uuid import UUID

from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.models import Role

ROLES: tuple[tuple[UUID, str, str, str], ...] = (
    (
        UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        "SUPERADMIN",
        "Super Administrador",
        "Acceso total y configuración de parámetros globales.",
    ),
    (
        UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"),
        "ENCARGADO",
        "Encargado del Negocio",
        "Gestión de cotizaciones, overrides, aprobación de shows y reportes.",
    ),
    (
        UUID("c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33"),
        "OPERADOR",
        "Operador de Elenco / Campo",
        "Confirmación de cobro in-situ y reporte de extensiones de show.",
    ),
)


async def seed_roles() -> int:
    inserted = 0
    async with get_sessionmaker()() as session:
        for role_id, code, name, description in ROLES:
            if await session.get(Role, role_id) is None:
                session.add(Role(id=role_id, code=code, name=name, description=description))
                inserted += 1
        await session.commit()
    return inserted


def main() -> None:
    count = asyncio.run(seed_roles())
    print(f"roles insertados: {count}")


if __name__ == "__main__":
    main()
