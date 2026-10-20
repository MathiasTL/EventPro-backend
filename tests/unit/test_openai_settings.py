"""Ajustes del agente de OpenAI y su cableado en el contenedor."""

from collections.abc import Iterator

import pytest

from app.application.use_cases.bot.agent_engine import ConversationAgent
from app.core.config import Settings, get_settings
from app.infrastructure.adapters.secondary.external_services.openai.openai_language_model_adapter import (  # noqa: E501
    OpenAILanguageModelAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.di import containers


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    containers.clear_application_caches()
    yield
    containers.clear_application_caches()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, secret_key="s" * 40, **env)  # type: ignore[call-arg]


def test_defaults_leave_the_agent_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    settings = _settings()

    assert settings.openai_api_key is None
    assert settings.openai_model == "gpt-6-luna"
    assert settings.openai_timeout_seconds == 15
    assert settings.openai_enabled is False


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_key_keeps_the_agent_disabled(blank: str) -> None:
    assert _settings(openai_api_key=blank).openai_enabled is False


def test_a_key_enables_the_agent_and_stays_secret() -> None:
    settings = _settings(openai_api_key="sk-test")

    assert settings.openai_enabled is True
    assert "sk-test" not in repr(settings)


def test_without_a_key_the_bot_uses_menus_only() -> None:
    use_case = containers.get_handle_incoming_message_use_case()

    assert containers.get_conversation_agent() is None
    assert use_case._agent is None


def test_with_a_key_the_bot_gets_the_agent_on_the_openai_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "modelo-de-prueba")
    get_settings.cache_clear()

    use_case = containers.get_handle_incoming_message_use_case()

    agent = containers.get_conversation_agent()
    assert isinstance(agent, ConversationAgent)
    assert use_case._agent is agent
    model = containers.get_language_model_port()
    assert isinstance(model, OpenAILanguageModelAdapter)
    assert model._model == "modelo-de-prueba"


def test_building_the_model_without_a_key_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        containers.get_language_model_port()
