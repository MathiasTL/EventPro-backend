import logging
import re
from typing import cast

import structlog


class SignatureTokenFilter(logging.Filter):
    """Evita que el access log de Uvicorn conserve credenciales de firma."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = re.sub(r"(/contracts/sign/)[^/\s?]+", r"\1[redacted]", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                re.sub(r"(/contracts/sign/)[^/\s?]+", r"\1[redacted]", value)
                if isinstance(value, str)
                else value
                for value in record.args
            )
        return True


def configure_logging(log_level: str = "INFO") -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SignatureTokenFilter) for f in access_logger.filters):
        access_logger.addFilter(SignatureTokenFilter())
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(message)s",
        stream=None,
    )
    # httpx registra cada petición en INFO y la URL de búsqueda de contactos incluye el teléfono.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
