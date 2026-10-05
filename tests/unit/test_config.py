from app.core.config import Settings, get_settings


def test_settings_from_env_file():
    settings = get_settings()
    assert settings.api_v1_prefix == "/api/v1"
    assert len(settings.secret_key) >= 32
    assert settings.access_token_expire_minutes == 60
    assert settings.refresh_token_expire_days == 7


def test_cors_origins_parsed_as_list():
    origins = get_settings().cors_origins
    assert isinstance(origins, list)
    assert "http://localhost:3000" in origins


def test_settings_accepts_overrides():
    settings = Settings(
        secret_key="s" * 40,
        cors_origins="http://a.test, http://b.test",
        access_token_expire_minutes=15,
    )
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.access_token_expire_minutes == 15
