"""GET /conversations/stream: la autenticación se resuelve antes de abrir el stream."""

import time
from collections.abc import Iterator
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.core.config import get_settings
from app.core.security import JWT_ALGORITHM, create_access_token
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.sse import RETRY_FRAME, format_event
from app.infrastructure.di import containers
from app.main import create_app
from tests import auth_support

URL = "/api/v1/conversations/stream"
EVENT = ConversationEvent(ConversationEventType.CONVERSATION_UPDATED, {"id": 7})


class OneEventSubscription:
    def __init__(self) -> None:
        self.sent = False
        self.closed = False

    async def next_event(self, timeout: float) -> ConversationEvent | None:
        if not self.sent:
            self.sent = True
            return EVENT
        raise ConnectionError("redis down")

    async def close(self) -> None:
        self.closed = True


class OneEventSubscriber:
    def __init__(self) -> None:
        self.subscriptions: list[OneEventSubscription] = []

    async def subscribe(self) -> OneEventSubscription:
        subscription = OneEventSubscription()
        self.subscriptions.append(subscription)
        return subscription


@pytest.fixture
def subscriber() -> OneEventSubscriber:
    return OneEventSubscriber()


@pytest.fixture
def app(subscriber: OneEventSubscriber) -> Iterator[FastAPI]:
    application = create_app()
    auth_support.install(application)
    application.dependency_overrides[containers.get_conversation_event_subscriber] = lambda: (
        subscriber
    )
    yield application
    auth_support.set_role(Role.SUPERADMIN)


def _token(*, expires_minutes: int = 60, subject: UUID | None = None) -> str:
    return create_access_token(
        subject=str(subject or uuid4()),
        role="ENCARGADO",
        secret_key=get_settings().secret_key,
        expires_minutes=expires_minutes,
    )


async def _get(app: FastAPI, params: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(URL, params=params)


async def test_it_streams_events_to_an_encargado(
    app: FastAPI, subscriber: OneEventSubscriber
) -> None:
    auth_support.set_role(Role.ENCARGADO)

    response = await _get(app, {"access_token": _token()})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text == RETRY_FRAME + format_event(EVENT)
    assert subscriber.subscriptions[0].closed


async def test_a_superadmin_is_allowed(app: FastAPI) -> None:
    auth_support.set_role(Role.SUPERADMIN)

    assert (await _get(app, {"access_token": _token()})).status_code == 200


async def test_it_rejects_a_missing_token_before_streaming(
    app: FastAPI, subscriber: OneEventSubscriber
) -> None:
    response = await _get(app, {})

    assert response.status_code == 401
    assert not response.headers["content-type"].startswith("text/event-stream")
    assert subscriber.subscriptions == []


@pytest.mark.parametrize("token", ["not-a-jwt", "x.y.z"])
async def test_it_rejects_an_invalid_token(app: FastAPI, token: str) -> None:
    assert (await _get(app, {"access_token": token})).status_code == 401


async def test_it_rejects_an_expired_token(app: FastAPI) -> None:
    expired = jwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) - 5},
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )

    assert (await _get(app, {"access_token": expired})).status_code == 401


async def test_it_rejects_a_token_without_exp(app: FastAPI) -> None:
    token = jwt.encode({"sub": str(uuid4())}, get_settings().secret_key, algorithm=JWT_ALGORITHM)

    assert (await _get(app, {"access_token": token})).status_code == 401


async def test_it_accepts_a_numeric_string_exp_like_regular_routes(app: FastAPI) -> None:
    token = jwt.encode(
        {"sub": str(uuid4()), "iat": int(time.time()), "exp": str(int(time.time()) + 300)},
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )

    assert (await _get(app, {"access_token": token})).status_code == 200


async def test_it_rejects_a_non_numeric_exp(app: FastAPI) -> None:
    token = jwt.encode(
        {"sub": str(uuid4()), "iat": int(time.time()), "exp": "soon"},
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )

    assert (await _get(app, {"access_token": token})).status_code == 401


async def test_it_rejects_an_inactive_account(app: FastAPI) -> None:
    auth_support.CURRENT.is_active = False
    try:
        assert (await _get(app, {"access_token": _token()})).status_code == 401
    finally:
        auth_support.CURRENT.is_active = True


async def test_it_rejects_an_operador_with_403_before_streaming(
    app: FastAPI, subscriber: OneEventSubscriber
) -> None:
    auth_support.set_role(Role.OPERADOR)

    response = await _get(app, {"access_token": _token()})

    assert response.status_code == 403
    assert not response.headers["content-type"].startswith("text/event-stream")
    assert subscriber.subscriptions == []
