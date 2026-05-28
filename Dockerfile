# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 10001 appuser

# Install Python deps first (layer cache friendly)
ARG TORCH_INDEX_URL=""
ARG APP_VERSION=""
COPY requirement_aiproofread.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r /app/requirements.txt \
    && if [ -n "${TORCH_INDEX_URL}" ]; then \
         pip install --no-compile --index-url "${TORCH_INDEX_URL}" torch; \
       else \
         pip install --no-compile torch; \
       fi

# Copy app code
COPY . /app

# Runtime env defaults (can be overridden by docker run -e)
ENV PORT=2302 \
    FLASK_ENV=production \
    GWORKERS=8 \
    GTHREADS=2 \
    TIMEOUT=120 \
    GRACEFUL_TIMEOUT=30 \
    KEEPALIVE=5 \
    LOG_LEVEL=info \
    APP_MODULE=wsgi:app \
    APP_VERSION=${APP_VERSION}

EXPOSE 2302

USER appuser

# Gunicorn entrypoint
CMD sh -c "gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers ${GWORKERS} \
    --threads ${GTHREADS} \
    --timeout ${TIMEOUT} \
    --graceful-timeout ${GRACEFUL_TIMEOUT} \
    --keep-alive ${KEEPALIVE} \
    --log-level ${LOG_LEVEL} \
    --access-logfile - \
    --error-logfile - \
    ${APP_MODULE}"
