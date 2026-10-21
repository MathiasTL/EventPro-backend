"""US-25: contrato compartido y API contra PostgreSQL temporal, sin servicios externos."""

from datetime import date
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.application.dtos.client_dto import FindClientsFilter
from app.application.use_cases.clients.find_clients import FindClientsUseCase
from app.application.use_cases.clients.get_client import GetClientUseCase
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_client_repository import (  # noqa: E501
    SqlAlchemyClientRepository,
)
from app.main import create_app
from tests.application.quote_ports_contract import FindClientsContract, GetClientContract

from ._support import run_migrations
from .test_real_quote_use_cases import RealHooks

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def migrated_url(database_url):
    run_migrations(database_url)
    return database_url


class ClientHooks(RealHooks):
    def seed_quote(self, status, **kwargs):
        # El gancho sin client_id representa un cliente ajeno en GetClientContract.
        if kwargs.get("client_id") is None:
            kwargs["client_id"] = self.seed_client("955111222", "Otro cliente")
        return super().seed_quote(status, **kwargs)


class TestRealFindClients(ClientHooks, FindClientsContract):
    def make_port(self):
        return FindClientsUseCase(SqlAlchemyClientRepository(self.session))

    async def test_empty_results_and_literal_search(self):
        self.seed_client("999888777", "Carlos")
        for query in ("No existe", "%", "_"):
            result = await self.make_port().execute(FindClientsFilter(q=query))
            assert result.items == () and result.total == 0

    async def test_exact_phone_and_name_filters_are_combined(self):
        self.seed_client("999888777", "Carlos")
        page = await self.make_port().execute(FindClientsFilter(q="María", phone="999888777"))
        assert page.total == 0
        with pytest.raises(ValidationError):
            await self.make_port().execute(FindClientsFilter(phone="teléfono inválido"))

    async def test_legacy_phone_is_found_and_normalized_without_writing(self):
        client_id = self.seed_client("999888777", "Carlos")
        with self.sync.begin() as connection:
            connection.execute(
                text("UPDATE clients SET phone='999888777' WHERE id=:id"), {"id": client_id}
            )
        for filters in (
            FindClientsFilter(phone="+51 999-888-777"),
            FindClientsFilter(phone="0051999888777"),
            FindClientsFilter(q="+51 999-888-777"),
            FindClientsFilter(q="888"),
        ):
            page = await self.make_port().execute(filters)
            assert [item.id for item in page.items] == [client_id]
            assert page.items[0].phone == "+51999888777"
        with Session(self.sync) as session:
            assert session.get(ClientModel, client_id).phone == "999888777"

    async def test_pages_are_stable_when_timestamps_match(self):
        for number in range(3):
            self.seed_client(f"95500000{number}", f"Cliente {number}")
        with self.sync.begin() as connection:
            connection.execute(text("UPDATE clients SET created_at='2026-10-01T00:00:00Z'"))
        port = self.make_port()
        first = await port.execute(FindClientsFilter(page=1, page_size=2))
        second = await port.execute(FindClientsFilter(page=2, page_size=2))
        repeated = await port.execute(FindClientsFilter(page=1, page_size=2))
        assert first == repeated
        assert first.total == second.total == 3
        assert len({item.id for item in (*first.items, *second.items)}) == 3

    async def test_read_use_case_never_commits_the_callers_transaction(self):
        client_id = uuid4()
        self.session.add(ClientModel(id=client_id, phone="+51999888777", full_name="Sin commit"))
        await self.session.flush()
        page = await self.make_port().execute(FindClientsFilter())
        assert [item.id for item in page.items] == [client_id]
        with Session(self.sync) as session:
            assert session.get(ClientModel, client_id) is None
        await self.session.rollback()
        with Session(self.sync) as session:
            assert session.get(ClientModel, client_id) is None


class TestRealGetClient(ClientHooks, GetClientContract):
    def make_port(self):
        return GetClientUseCase(SqlAlchemyClientRepository(self.session))

    async def test_empty_history_and_quotes_ordered_by_event_date(self):
        client_id = self.seed_client("999888777", "Carlos")
        assert (await self.make_port().execute(client_id)).quotes == ()
        older = self.seed_quote(
            QuoteStatus.CANCELLED, client_id=client_id, event_date=date(2026, 10, 15)
        )
        newer = self.seed_quote(
            QuoteStatus.SENT, client_id=client_id, event_date=date(2026, 11, 15)
        )
        detail = await self.make_port().execute(client_id)
        assert [quote.quote_id for quote in detail.quotes] == [newer, older]


class TestClientHttp(ClientHooks):
    @pytest.fixture
    async def http(self):
        self.app = create_app()
        self.auth = AuthContext(self.user_id, Role.ENCARGADO)
        self.app.dependency_overrides[get_auth_context] = lambda: self.auth

        async def read():
            async with AsyncSession(self.engine) as session:
                yield session

        self.app.dependency_overrides[get_session] = read
        async with AsyncClient(
            transport=ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client

    async def test_list_and_detail_use_the_existing_response_contract(self, http):
        client_id = self.seed_client("999888777", "Carlos")
        quote_id = self.seed_quote(QuoteStatus.SENT, client_id=client_id)
        result = await http.get("/api/v1/clients", params={"phone": "999 888 777"})
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 1
        assert result.json()["items"][0]["phone"] == "+51999888777"
        detail = await http.get(f"/api/v1/clients/{client_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["quotes"][0]["quote_id"] == str(quote_id)
        assert isinstance(detail.json()["quotes"][0]["total_amount"], str)
        with Session(self.sync) as session:
            assert len(session.scalars(select(ClientModel)).all()) == 1

    async def test_roles_and_authentication_are_enforced_for_both_endpoints(self, http):
        client_id = self.seed_client("999888777", "Carlos")
        for role in (Role.ENCARGADO, Role.SUPERADMIN):
            self.auth = AuthContext(self.user_id, role)
            for path in ("/api/v1/clients", f"/api/v1/clients/{client_id}"):
                assert (await http.get(path)).status_code == 200
        self.auth = AuthContext(self.user_id, Role.OPERADOR)
        for path in ("/api/v1/clients", f"/api/v1/clients/{client_id}"):
            assert (await http.get(path)).status_code == 403
        self.app.dependency_overrides.pop(get_auth_context)
        for path in ("/api/v1/clients", f"/api/v1/clients/{client_id}"):
            assert (await http.get(path)).status_code == 401

    async def test_not_found_invalid_filters_and_no_create_endpoint(self, http):
        assert (await http.get(f"/api/v1/clients/{uuid4()}")).status_code == 404
        assert (await http.get("/api/v1/clients/invalid-uuid")).status_code == 422
        for params in ({"page": 0}, {"page_size": 101}, {"phone": "invalid"}):
            assert (await http.get("/api/v1/clients", params=params)).status_code == 422
        assert (await http.post("/api/v1/clients", json={})).status_code == 405
