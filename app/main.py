"""Aplicación FastAPI mínima para que los routers de E5 puedan probarse."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings
from app.infrastructure.adapters.primary.web.payments_router import router as payments_router

app = FastAPI(title=settings.app_name, docs_url="/docs")
app.include_router(payments_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
