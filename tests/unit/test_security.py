from datetime import UTC, timedelta
from datetime import datetime as dt

import jwt
import pytest

from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)

SECRET = "unit-test-secret-key-with-more-than-32-characters!"


def test_hash_password_roundtrip():
    password_hash = hash_password("PasswordSeguro123!")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("PasswordSeguro123!", password_hash) is True
    assert verify_password("PasswordIncorrecta999!", password_hash) is False


def test_hash_password_is_salted():
    assert hash_password("misma-clave") != hash_password("misma-clave")


def test_create_access_token_claims():
    token = create_access_token(
        subject="b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        role="SUPERADMIN",
        secret_key=SECRET,
        expires_minutes=60,
    )
    claims = decode_access_token(token, SECRET)
    assert claims["sub"] == "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"
    assert claims["role"] == "SUPERADMIN"
    assert claims["exp"] - claims["iat"] == 60 * 60


def test_decode_access_token_rejects_wrong_secret():
    token = create_access_token(subject="u", role="OPERADOR", secret_key=SECRET)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, "otra-clave-distinta-con-32-chars-min!!")


def test_decode_access_token_rejects_expired():
    now = dt.now(UTC)
    payload = {
        "sub": "u",
        "role": "ENCARGADO",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    token = jwt.encode(payload, SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, SECRET)


def test_new_refresh_token_is_unique_32_hex():
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b
    assert len(a) == 32
    assert all(c in "0123456789abcdef" for c in a)


def test_hash_refresh_token_is_sha256_hex():
    digest = hash_refresh_token("token-valor")
    assert len(digest) == 64
    assert digest == hash_refresh_token("token-valor")
