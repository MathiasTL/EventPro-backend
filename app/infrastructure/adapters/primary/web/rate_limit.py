from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.infrastructure.adapters.primary.web.problem import problem_response


def _redis_storage_uri() -> str:
    settings = get_settings()
    auth = f":{quote(settings.redis_password, safe='')}@" if settings.redis_password else ""
    return f"redis://{auth}{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"


# ADR-09: slowapi con almacenamiento en Redis (fallback a memoria si Redis cae).
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_storage_uri(),
    headers_enabled=True,
    swallow_errors=True,
    in_memory_fallback_enabled=True,
    key_prefix="eventpro:ratelimit",
)


def install_rate_limit(app: FastAPI) -> None:
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> Response:
        response: Response = problem_response(
            request,
            429,
            "rate-limit-exceeded",
            "Límite de peticiones excedido",
            "Demasiadas peticiones a este endpoint. Intenta de nuevo más tarde.",
        )
        current_limit = getattr(request.state, "view_rate_limit", None)
        if current_limit is not None:
            response = limiter._inject_headers(response, current_limit)
        return response
