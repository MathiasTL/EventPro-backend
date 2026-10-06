from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.application.ports.output.cache_port import ICachePort
from app.application.ports.output.repository_health_port import IRepositoryHealthPort
from app.infrastructure.di.containers import get_cache_port, get_repository_health_port

router = APIRouter(tags=["Salud"])


@router.get("/health")
async def health(
    repository: Annotated[IRepositoryHealthPort, Depends(get_repository_health_port)],
    cache: Annotated[ICachePort, Depends(get_cache_port)],
) -> JSONResponse:
    database_ok = await repository.ping()
    redis_ok = await cache.ping()
    checks = {
        "database": "ok" if database_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    healthy = database_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
