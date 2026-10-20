"""Regresión del catálogo: carga de relaciones y commit antes de la respuesta HTTP."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog_client(infra):
    factory = get_sessionmaker()
    actor = uuid4()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO roles(code,name) VALUES ('SUPERADMIN','Admin') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.execute(
            text(
                "INSERT INTO users(id,role_id,full_name,email,phone,hashed_password) "
                "SELECT :id,id,'Admin',:email,:phone,'test' FROM roles WHERE code='SUPERADMIN'"
            ),
            {"id": actor, "email": f"{actor}@test.invalid", "phone": actor.hex[:20]},
        )
        await session.commit()
    token = create_access_token(
        subject=str(actor), role="SUPERADMIN", secret_key=get_settings().secret_key
    )
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client, factory


def package_payload():
    return {
        "name": f"Paquete-{uuid4()}",
        "service_category": "SHOW",
        "base_price": "100.00",
        "direct_cost": "50.00",
        "duration_minutes": 90,
    }


async def test_created_package_persists_and_empty_themes_do_not_lazy_load(catalog_client):
    client, factory = catalog_client
    payload = package_payload()
    created = await client.post("/api/v1/catalog/packages", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["compatible_themes"] == []
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT name FROM packages WHERE id=:id"), {"id": created.json()["id"]}
            )
            == payload["name"]
        )


async def test_update_package_eager_loads_existing_themes(catalog_client):
    client, factory = catalog_client
    payload = package_payload()
    created = await client.post("/api/v1/catalog/packages", json=payload)
    assert created.status_code == 201, created.text
    identifier = created.json()["id"]
    theme_id = uuid4()
    async with factory() as session:
        await session.execute(
            text("INSERT INTO themes(id,name) VALUES (:id,:name)"),
            {"id": theme_id, "name": f"Tema-{theme_id}"},
        )
        await session.execute(
            text("INSERT INTO package_themes(package_id,theme_id) VALUES (:package,:theme)"),
            {"package": identifier, "theme": theme_id},
        )
        await session.commit()
    payload["base_price"] = "120.00"
    updated = await client.patch(f"/api/v1/catalog/packages/{identifier}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["compatible_themes"][0]["id"] == str(theme_id)
    async with factory() as session:
        assert (
            str(
                await session.scalar(
                    text("SELECT base_price FROM packages WHERE id=:id"), {"id": identifier}
                )
            )
            == "120.00"
        )


async def test_failed_commit_returns_500_and_does_not_persist(catalog_client):
    client, factory = catalog_client
    payload = package_payload()

    def fail_commit(session):
        raise RuntimeError("Fallo de commit simulado")

    event.listen(Session, "before_commit", fail_commit)
    try:
        result = await client.post("/api/v1/catalog/packages", json=payload)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM packages WHERE name=:name"), {"name": payload["name"]}
            )
            == 0
        )


async def test_theme_and_crew_mutations_persist(catalog_client):
    client, factory = catalog_client
    theme_name = f"Tema-{uuid4()}"
    theme = await client.post("/api/v1/catalog/themes", json={"name": theme_name})
    assert theme.status_code == 201, theme.text
    crew = await client.post(
        "/api/v1/crews",
        json={"leader_name": "Líder", "phone": "+51999999999", "service_category": "SHOW"},
    )
    assert crew.status_code == 201, crew.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT name FROM themes WHERE id=:id"), {"id": theme.json()["id"]}
            )
            == theme_name
        )
        assert (
            await session.scalar(
                text("SELECT leader_name FROM crews WHERE id=:id"), {"id": crew.json()["id"]}
            )
            == "Líder"
        )
