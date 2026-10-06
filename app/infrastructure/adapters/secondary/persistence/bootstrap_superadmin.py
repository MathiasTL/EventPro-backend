"""Comando de arranque del usuario SUPERADMIN (Docs/03-datos, sección 4).

Uso:
    SUPERADMIN_EMAIL=admin@eventpro.pe SUPERADMIN_PASSWORD='<contraseña-segura>' \
      python -m app.infrastructure.adapters.secondary.persistence.bootstrap_superadmin

Reglas: idempotente, falla cerrada (códigos de salida distintos de 0), valores por
defecto de full_name/phone, y nunca imprime la contraseña.
"""

import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_ROLE_MISSING = 3
EXIT_DB_ERROR = 4

MIN_PASSWORD_LENGTH = 12
DEFAULT_FULL_NAME = "Super Administrador"
DEFAULT_PHONE = "+51000000000"
SUPERADMIN_ROLE = "SUPERADMIN"


def validate(email: str, password: str) -> int | None:
    """Valida la configuración; devuelve el código de salida o None si es válida."""
    if not email.strip():
        print("Falta SUPERADMIN_EMAIL.", file=sys.stderr)
        return EXIT_CONFIG
    if len(password) < MIN_PASSWORD_LENGTH:
        # Nunca imprimir la contraseña.
        print(
            f"SUPERADMIN_PASSWORD débil o ausente: mínimo {MIN_PASSWORD_LENGTH} caracteres.",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    return None


async def bootstrap(email: str, password: str) -> int:
    """Crea el SUPERADMIN si no existe; idempotente."""
    normalized_email = email.strip().lower()
    async with get_sessionmaker()() as session:
        role_id = (
            await session.execute(select(RoleModel.id).where(RoleModel.code == SUPERADMIN_ROLE))
        ).scalar_one_or_none()
        if role_id is None:
            print(
                f"El rol {SUPERADMIN_ROLE} aún no fue sembrado (ejecuta el seed de roles).",
                file=sys.stderr,
            )
            return EXIT_ROLE_MISSING
        existing = (
            await session.execute(
                select(UserModel.id).where(func.lower(UserModel.email) == normalized_email)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return EXIT_OK
        session.add(
            UserModel(
                role_id=role_id,
                full_name=DEFAULT_FULL_NAME,
                email=normalized_email,
                phone=DEFAULT_PHONE,
                hashed_password=hash_password(password),
                is_active=True,
            )
        )
        await session.commit()
    print(f"SUPERADMIN creado: {normalized_email}")
    return EXIT_OK


def main() -> int:
    settings = get_settings()
    invalid = validate(settings.superadmin_email, settings.superadmin_password)
    if invalid is not None:
        return invalid
    try:
        return asyncio.run(bootstrap(settings.superadmin_email, settings.superadmin_password))
    except Exception as exc:
        print(f"Error creando SUPERADMIN: {exc}", file=sys.stderr)
        return EXIT_DB_ERROR


if __name__ == "__main__":
    sys.exit(main())
