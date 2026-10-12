"""Verificación de la firma del webhook de cuenta de Chatwoot.

Chatwoot firma ``"{X-Chatwoot-Timestamp}.{cuerpo_crudo}"`` con HMAC-SHA256 y envía el resultado
como ``X-Chatwoot-Signature: sha256=<hex>``. La función es pura: recibe bytes y un instante, no
lee la petición ni el reloj, y nunca incluye secretos ni firmas en lo que devuelve.
"""

import hashlib
import hmac
from datetime import datetime
from enum import StrEnum

SIGNATURE_PREFIX = "sha256="
DEFAULT_TOLERANCE_SECONDS = 300


class SignatureCheck(StrEnum):
    """Resultado de la verificación; el valor es lo único que se registra al rechazar."""

    VALID = "valid"
    MISSING_HEADER = "missing_header"
    BAD_TIMESTAMP = "bad_timestamp"
    STALE_TIMESTAMP = "stale_timestamp"
    MISMATCH = "mismatch"
    SECRET_NOT_CONFIGURED = "secret_not_configured"


def verify_chatwoot_signature(
    secret: str,
    timestamp: str | None,
    raw_body: bytes,
    signature: str | None,
    now: datetime,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> SignatureCheck:
    """Valida firma y antigüedad sobre los bytes exactos del cuerpo.

    Sin secreto configurado rechaza todo (falla cerrado). El timestamp son segundos Unix en
    dígitos ASCII y la ventana es simétrica: se rechazan también los instantes futuros.
    """

    if not secret:
        return SignatureCheck.SECRET_NOT_CONFIGURED
    if not timestamp or not signature:
        return SignatureCheck.MISSING_HEADER
    if not (timestamp.isascii() and timestamp.isdigit()):
        return SignatureCheck.BAD_TIMESTAMP
    if abs(now.timestamp() - int(timestamp)) > tolerance_seconds:
        return SignatureCheck.STALE_TIMESTAMP

    signed = timestamp.encode() + b"." + raw_body
    expected = SIGNATURE_PREFIX + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    # Se comparan bytes: ``compare_digest`` con ``str`` falla ante caracteres no ASCII.
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return SignatureCheck.MISMATCH
    return SignatureCheck.VALID
