# ---------- Frontend build stage ----------
FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# The SPA is served by FastAPI on the same origin, so the API is relative.
ENV VITE_API_URL=/api
RUN npm run build

# ---------- Backend runtime ----------
FROM python:3.12-slim

WORKDIR /app

ARG MONITORAI_BUILD_SHA=""
ARG MONITORAI_BUILD_TIME=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    MONITORAI_BUILD_SHA=${MONITORAI_BUILD_SHA} \
    MONITORAI_BUILD_TIME=${MONITORAI_BUILD_TIME}

LABEL org.opencontainers.image.title="MonitorAI V2.2" \
      org.opencontainers.image.version="2.2" \
      org.opencontainers.image.revision=${MONITORAI_BUILD_SHA} \
      org.opencontainers.image.created=${MONITORAI_BUILD_TIME}

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .

# Built frontend; FastAPI serves it from /app/static
COPY --from=frontend-build /frontend/dist ./static

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Migrations run inside the app's startup hook (app/main.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
