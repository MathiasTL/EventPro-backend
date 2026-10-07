"""Smoke test: las rutas de catálogo, elencos y overrides quedan expuestas."""

from __future__ import annotations

from app.main import create_app


def _paths() -> set[str]:
    return set(create_app().openapi()["paths"])


def test_catalog_routes_are_registered() -> None:
    paths = _paths()
    for expected in (
        "/api/v1/catalog/packages",
        "/api/v1/catalog/packages/{package_id}",
        "/api/v1/catalog/packages/{package_id}/inventory-items",
        "/api/v1/catalog/packages/{package_id}/themes",
        "/api/v1/catalog/themes",
        "/api/v1/catalog/extras",
        "/api/v1/catalog/inventory-items",
    ):
        assert expected in paths, expected


def test_crew_and_override_routes_are_registered() -> None:
    paths = _paths()
    assert "/api/v1/crews" in paths
    assert "/api/v1/crews/{crew_id}" in paths
    assert "/api/v1/overrides/payments/{payment_id}/approve-simultaneous" in paths
