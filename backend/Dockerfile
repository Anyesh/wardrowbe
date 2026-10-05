FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements-extras.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-extras.txt

# REMBG_HOME is outside /root because the app runs as non-root uids. The models dir is
# 1777 because PUID remapping changes appuser's numeric uid, so a build-time chown would not survive.
ARG BG_REMOVAL_MODEL=u2net
ENV REMBG_HOME=/opt/rembg
RUN python -c "from rembg import new_session; new_session('$BG_REMOVAL_MODEL')" \
    && chmod -R a+rX /opt/rembg \
    && chmod 1777 /opt/rembg/models

# Set after the bake so root does not create the directory and lock out other uids.
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

# Copy application code
COPY . .

# Create non-root user and storage directory
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
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
