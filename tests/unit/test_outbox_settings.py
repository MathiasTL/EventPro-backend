"""Valores de OUTBOX_* y su documentación en .env.example."""

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.domain.value_objects.outbox import DEFAULT_MAX_ATTEMPTS

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_NAMES = ("OUTBOX_BATCH_SIZE", "OUTBOX_LEASE_SECONDS", "OUTBOX_MAX_ATTEMPTS")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings() -> Settings:
    return Settings(secret_key="s" * 40, _env_file=None)  # type: ignore[call-arg]


def test_defaults_match_the_spec(clean_env: pytest.MonkeyPatch) -> None:
    settings = _settings()
    assert settings.outbox_batch_size == 20
    assert settings.outbox_lease_seconds == 60
    assert settings.outbox_max_attempts == 6
    assert settings.outbox_max_attempts == DEFAULT_MAX_ATTEMPTS


def test_values_can_be_overridden_by_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("OUTBOX_BATCH_SIZE", "5")
    clean_env.setenv("OUTBOX_LEASE_SECONDS", "120")
    clean_env.setenv("OUTBOX_MAX_ATTEMPTS", "3")
    settings = _settings()
    assert (settings.outbox_batch_size, settings.outbox_lease_seconds) == (5, 120)
    assert settings.outbox_max_attempts == 3


@pytest.mark.parametrize("name", _NAMES)
def test_non_positive_values_are_rejected(clean_env: pytest.MonkeyPatch, name: str) -> None:
    clean_env.setenv(name, "0")
    with pytest.raises(PydanticValidationError):
        _settings()


def test_env_example_documents_the_same_defaults() -> None:
    values: dict[str, str] = {}
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    defaults = {
        "OUTBOX_BATCH_SIZE": Settings.model_fields["outbox_batch_size"].default,
        "OUTBOX_LEASE_SECONDS": Settings.model_fields["outbox_lease_seconds"].default,
        "OUTBOX_MAX_ATTEMPTS": Settings.model_fields["outbox_max_attempts"].default,
    }
    for name, default in defaults.items():
        assert name in values, f"{name} falta en .env.example"
        assert int(values[name]) == default
