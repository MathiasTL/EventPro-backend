from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.adapters.primary.web import auth_router, health_router
from app.infrastructure.adapters.primary.web.problem import install_exception_handlers
from app.infrastructure.adapters.primary.web.rate_limit import install_rate_limit
from app.infrastructure.adapters.primary.web.v1 import (
    budgets_router,
    catalog_router,
    crew_router,
    events_router,
    manual_bookings_router,
    overrides_router,
    payments_router,
)
from app.infrastructure.di.containers import shutdown_infrastructure

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    await shutdown_infrastructure()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="EventPro API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def add_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    install_exception_handlers(application)
    install_rate_limit(application)
    application.include_router(health_router.router)
    application.include_router(auth_router.router, prefix=settings.api_v1_prefix)
    application.include_router(events_router.router, prefix=settings.api_v1_prefix)
    application.include_router(catalog_router.router, prefix=settings.api_v1_prefix)
    application.include_router(crew_router.router, prefix=settings.api_v1_prefix)
    application.include_router(overrides_router.router, prefix=settings.api_v1_prefix)
    application.include_router(payments_router.router, prefix=settings.api_v1_prefix)
    application.include_router(budgets_router.router, prefix=settings.api_v1_prefix)
    application.include_router(manual_bookings_router.router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
