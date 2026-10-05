"""Comando bootstrap del SUPERADMIN (Docs/03-datos, sección 4)."""

from sqlalchemy import func, select
from sqlalchemy import text as sql_text

from app.core.config import get_settings
from app.core.security import verify_password
from app.infrastructure.adapters.secondary.persistence.bootstrap_superadmin import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_ROLE_MISSING,
    bootstrap,
    main,
    validate,
)
from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User as UserModel

STRONG_PASSWORD = "Contraseña-Segura-123!"


async def _seed_roles() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            sql_text(
                "INSERT INTO roles (code, name) VALUES "
                "('SUPERADMIN', 'Super Administrador'), "
                "('ENCARGADO', 'Encargado'), "
                "('OPERADOR', 'Operador') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.commit()


def test_validate_rejects_weak_or_missing_password() -> None:
    assert validate("admin@eventpro.pe", "admin123") == EXIT_CONFIG
    assert validate("admin@eventpro.pe", "") == EXIT_CONFIG
    assert validate("  ", STRONG_PASSWORD) == EXIT_CONFIG
    assert validate("admin@eventpro.pe", STRONG_PASSWORD) is None


def test_main_returns_config_error_with_weak_password(monkeypatch) -> None:
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "corta123")
    get_settings.cache_clear()
    try:
        assert main() == EXIT_CONFIG
    finally:
        get_settings.cache_clear()


async def test_bootstrap_creates_superadmin_and_is_idempotent(infra: None) -> None:
    await _seed_roles()
    email = "sb-superadmin@eventpro.pe"

    first = await bootstrap(email, STRONG_PASSWORD)
    second = await bootstrap(email, STRONG_PASSWORD)

    assert first == EXIT_OK
    assert second == EXIT_OK
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(UserModel, RoleModel.code)
                .join(RoleModel, UserModel.role_id == RoleModel.id)
                .where(func.lower(UserModel.email) == email)
            )
        ).all()
        assert len(rows) == 1
        user, role_code = rows[0]
        assert role_code == "SUPERADMIN"
        assert user.full_name == "Super Administrador"
        assert user.phone == "+51000000000"
        assert verify_password(STRONG_PASSWORD, user.hashed_password)


async def test_bootstrap_fails_closed_when_role_missing(infra: None) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(sql_text("DELETE FROM users"))
        await session.execute(sql_text("DELETE FROM roles"))
        await session.commit()

    result = await bootstrap("sin-rol@eventpro.pe", STRONG_PASSWORD)

    assert result == EXIT_ROLE_MISSING
    async with get_sessionmaker()() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.email == "sin-rol@eventpro.pe")
            )
        ).scalar_one()
    assert count == 0
