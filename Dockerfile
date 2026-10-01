# Multi-stage Dockerfile para EventPro Backend (FastAPI / Python 3.12)

# --- Etapa Builder: compila e instala dependencias de runtime en un venv ---
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Solo dependencias de runtime; las de desarrollo viven en requirements-dev.txt
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Etapa Final / Runtime ---
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Librerias de sistema requeridas por WeasyPrint y asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios; /app/uploads le pertenece para escribir comprobantes y contratos
RUN groupadd --system --gid 10001 eventpro \
    && useradd --system --uid 10001 --gid eventpro --home-dir /app --shell /usr/sbin/nologin eventpro \
    && mkdir -p /app/uploads \
    && chown -R eventpro:eventpro /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=eventpro:eventpro . /app

USER eventpro

EXPOSE 8000

# Sonda de salud con la libreria estandar (sin curl); exige HTTP 200 en /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

# Produccion: sin --reload (el modo desarrollo se define en docker-compose.override.yml)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
