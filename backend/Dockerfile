FROM python:3.11-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

# Keep the environment outside /app so the development bind mount cannot hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    REMBG_HOME=/opt/rembg \
    PATH="/opt/venv/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Install the locked production dependencies without the test and lint tools.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra background-removal

# Pre-download the same model selected by the application default.
RUN python -c "from rembg import new_session; new_session('u2net')"

# Copy application code
COPY . .

# Create non-root user and storage directory
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /opt/rembg
RUN mkdir -p /data/wardrobe /data/uploads && chown -R appuser:appuser /data

# Entrypoint drops to appuser (remapped to PUID/PGID when set); when the
# container is started as a non-root uid (e.g. k8s runAsUser) it execs directly
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS development
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra background-removal

FROM base AS production
