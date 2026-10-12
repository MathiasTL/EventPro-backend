"""Valores de CHATWOOT_*: valores por defecto, normalización y reglas de consistencia."""

import pytest
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.infrastructure.adapters.primary.jobs.worker import CYCLE_TIMEOUT_SECONDS

_NAMES = (
    "CHATWOOT_BASE_URL",
    "CHATWOOT_ACCOUNT_ID",
    "CHATWOOT_INBOX_ID",
    "CHATWOOT_BOT_TOKEN",
    "CHATWOOT_AGENT_TOKEN",
    "CHATWOOT_WEBHOOK_SECRET",
    "CHATWOOT_TIMEOUT_SECONDS",
    "CHATWOOT_CONNECT_TIMEOUT_SECONDS",
    "CHATWOOT_TEMPLATE_LANGUAGE",
    "CHATWOOT_TEMPLATE_CATEGORY",
)
_BOT_TOKEN = "bot-token-value-1234"
_AGENT_TOKEN = "agent-token-value-5678"
_SECRET = "webhook-secret-value-9012"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings() -> Settings:
    return Settings(secret_key="s" * 40, _env_file=None)  # type: ignore[call-arg]


def _configure(env: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {
        "CHATWOOT_BASE_URL": "https://chatwoot.example.org",
        "CHATWOOT_ACCOUNT_ID": "1",
        "CHATWOOT_INBOX_ID": "2",
        "CHATWOOT_BOT_TOKEN": _BOT_TOKEN,
        "CHATWOOT_AGENT_TOKEN": _AGENT_TOKEN,
        "CHATWOOT_WEBHOOK_SECRET": _SECRET,
    }
    values.update(overrides)
    for name, value in values.items():
        env.setenv(name, value)


def test_defaults_build_without_any_chatwoot_variable(clean_env: pytest.MonkeyPatch) -> None:
    settings = _settings()
    assert settings.chatwoot_base_url == ""
    assert settings.chatwoot_account_id is None
    assert settings.chatwoot_inbox_id is None
    assert settings.chatwoot_bot_token.get_secret_value() == ""
    assert settings.chatwoot_agent_token.get_secret_value() == ""
    assert settings.chatwoot_webhook_secret.get_secret_value() == ""
    assert settings.chatwoot_enabled is False
    assert settings.chatwoot_timeout_seconds == 10.0
    assert settings.chatwoot_connect_timeout_seconds == 3.0
    assert settings.chatwoot_template_language == "es"
    assert settings.chatwoot_template_category == "UTILITY"


@pytest.mark.parametrize("name", ["CHATWOOT_ACCOUNT_ID", "CHATWOOT_INBOX_ID"])
def test_blank_ids_become_none(clean_env: pytest.MonkeyPatch, name: str) -> None:
    clean_env.setenv(name, "  ")
    settings = _settings()
    assert settings.chatwoot_account_id is None
    assert settings.chatwoot_inbox_id is None


def test_base_url_trailing_slash_is_stripped(clean_env: pytest.MonkeyPatch) -> None:
    _configure(clean_env, CHATWOOT_BASE_URL="https://chatwoot.example.org///")
    assert _settings().chatwoot_base_url == "https://chatwoot.example.org"


@pytest.mark.parametrize("value", ["chatwoot.example.org", "ftp://chatwoot.example.org"])
def test_base_url_must_be_http(clean_env: pytest.MonkeyPatch, value: str) -> None:
    _configure(clean_env, CHATWOOT_BASE_URL=value)
    with pytest.raises(PydanticValidationError, match="CHATWOOT_BASE_URL"):
        _settings()


def test_chatwoot_is_enabled_by_the_base_url(clean_env: pytest.MonkeyPatch) -> None:
    assert _settings().chatwoot_enabled is False
    _configure(clean_env)
    settings = _settings()
    assert settings.chatwoot_enabled is True
    assert settings.chatwoot_account_id == 1
    assert settings.chatwoot_inbox_id == 2


def test_secrets_are_masked(clean_env: pytest.MonkeyPatch) -> None:
    _configure(clean_env)
    settings = _settings()
    assert isinstance(settings.chatwoot_bot_token, SecretStr)
    assert isinstance(settings.chatwoot_agent_token, SecretStr)
    assert isinstance(settings.chatwoot_webhook_secret, SecretStr)
    rendered = f"{settings!r} {settings!s}"
    for value in (_BOT_TOKEN, _AGENT_TOKEN, _SECRET):
        assert value not in rendered
    assert settings.chatwoot_bot_token.get_secret_value() == _BOT_TOKEN


@pytest.mark.parametrize(
    "missing",
    [
        "CHATWOOT_ACCOUNT_ID",
        "CHATWOOT_INBOX_ID",
        "CHATWOOT_BOT_TOKEN",
        "CHATWOOT_AGENT_TOKEN",
    ],
)
def test_base_url_requires_the_rest_of_the_configuration(
    clean_env: pytest.MonkeyPatch, missing: str
) -> None:
    _configure(clean_env)
    clean_env.delenv(missing)
    with pytest.raises(PydanticValidationError) as error:
        _settings()
    message = str(error.value)
    assert missing in message
    for value in (_BOT_TOKEN, _AGENT_TOKEN, _SECRET):
        assert value not in message


def test_consistency_error_lists_every_missing_name(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("CHATWOOT_BASE_URL", "https://chatwoot.example.org")
    with pytest.raises(PydanticValidationError) as error:
        _settings()
    message = str(error.value)
    for name in (
        "CHATWOOT_ACCOUNT_ID",
        "CHATWOOT_INBOX_ID",
        "CHATWOOT_BOT_TOKEN",
        "CHATWOOT_AGENT_TOKEN",
    ):
        assert name in message


def test_webhook_secret_stays_optional_in_development(clean_env: pytest.MonkeyPatch) -> None:
    _configure(clean_env)
    clean_env.delenv("CHATWOOT_WEBHOOK_SECRET")
    assert _settings().chatwoot_enabled is True


@pytest.mark.parametrize("name", ["CHATWOOT_TIMEOUT_SECONDS", "CHATWOOT_CONNECT_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_timeouts_must_be_positive(clean_env: pytest.MonkeyPatch, name: str, value: str) -> None:
    clean_env.setenv(name, value)
    with pytest.raises(PydanticValidationError):
        _settings()


def test_default_timeout_fits_in_one_dispatch_cycle(clean_env: pytest.MonkeyPatch) -> None:
    # Un envío hace hasta cuatro llamadas HTTP seguidas (búsqueda, contacto, conversación, mensaje).
    assert 4 * _settings().chatwoot_timeout_seconds < CYCLE_TIMEOUT_SECONDS


# --- Entornos con configuración obligatoria (staging y producción) ---------------------------

_MANDATORY = (
    "CHATWOOT_BASE_URL",
    "CHATWOOT_ACCOUNT_ID",
    "CHATWOOT_INBOX_ID",
    "CHATWOOT_BOT_TOKEN",
    "CHATWOOT_AGENT_TOKEN",
    "CHATWOOT_WEBHOOK_SECRET",
)


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_require_every_chatwoot_variable(
    clean_env: pytest.MonkeyPatch, app_env: str
) -> None:
    clean_env.setenv("APP_ENV", app_env)
    with pytest.raises(PydanticValidationError) as error:
        _settings()
    message = str(error.value)
    for name in _MANDATORY:
        assert name in message


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize("missing", _MANDATORY)
def test_staging_and_production_name_only_the_missing_variable(
    clean_env: pytest.MonkeyPatch, app_env: str, missing: str
) -> None:
    clean_env.setenv("APP_ENV", app_env)
    _configure(clean_env)
    clean_env.delenv(missing)
    with pytest.raises(PydanticValidationError) as error:
        _settings()
    message = str(error.value)
    assert missing in message
    for name in _MANDATORY:
        if name != missing:
            assert name not in message
    for value in (_BOT_TOKEN, _AGENT_TOKEN, _SECRET):
        assert value not in message


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_build_with_the_complete_configuration(
    clean_env: pytest.MonkeyPatch, app_env: str
) -> None:
    clean_env.setenv("APP_ENV", app_env)
    _configure(clean_env)
    assert _settings().chatwoot_enabled is True


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_development_and_test_keep_chatwoot_optional(
    clean_env: pytest.MonkeyPatch, app_env: str
) -> None:
    clean_env.setenv("APP_ENV", app_env)
    assert _settings().chatwoot_enabled is False
