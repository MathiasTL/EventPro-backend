import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

PASSWORD_HASH = PasswordHash.recommended()

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return PASSWORD_HASH.verify(password, password_hash)


def create_access_token(
    *,
    subject: str,
    role: str,
    secret_key: str,
    expires_minutes: int = 60,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict[str, object]:
    return jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])


def new_refresh_token() -> str:
    return uuid.uuid4().hex


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
