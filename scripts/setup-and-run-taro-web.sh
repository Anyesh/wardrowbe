#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE="${ROOT_DIR}/.env.local-dev"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
BACKEND_SERVICES=(postgres redis backend worker)
TARO_WEB_PORT=${TARO_WEB_PORT:-10086}
BACKEND_PORT=${BACKEND_PORT:-8000}
TARO_APP_API_BASE_URL=${TARO_APP_API_BASE_URL:-"http://localhost:${BACKEND_PORT}"}
START_NEXT_FRONTEND=${START_NEXT_FRONTEND:-0}
SKIP_INSTALL=${SKIP_INSTALL:-0}
RUN_SETUP_ONLY=0
RUN_START_ONLY=0
SKIP_MIGRATIONS=${SKIP_MIGRATIONS:-0}
LOCAL_PG_USER=${LOCAL_PG_USER:-$(id -un)}
LOCAL_DATABASE_URL=${LOCAL_DATABASE_URL:-"postgresql+asyncpg://${LOCAL_PG_USER}@localhost:5432/wardrobe"}
LOCAL_REDIS_URL=${LOCAL_REDIS_URL:-"redis://localhost:6379/0"}
LOCAL_BACKEND_PID=""
USE_DOCKER=0
LOCAL_CORS_ORIGINS_JSON=$(printf '["http://localhost:3000","http://localhost:%s","http://127.0.0.1:%s"]' "$TARO_WEB_PORT" "$TARO_WEB_PORT")

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

One-click local bootstrap for Wardrowbe backend + Taro H5 web app.

Options:
  --setup-only         Prepare env, install deps, and start backend services only
  --start-only         Skip env generation and dependency installation
  --with-next-frontend Also start the Next.js frontend container when Docker is available
  --skip-install       Skip pnpm/corepack and backend venv install steps
  --skip-migrations    Skip alembic upgrade head
  -h, --help           Show this help

Environment overrides:
  TARO_WEB_PORT        H5 dev server port (default: 10086)
  BACKEND_PORT         Backend port (default: 8000)
  TARO_APP_API_BASE_URL API base URL for the Taro app (default: http://localhost:BACKEND_PORT)
  LOCAL_PG_USER        Local PostgreSQL user for non-Docker mode (default: current user)
  LOCAL_DATABASE_URL   Override local backend DATABASE_URL
  LOCAL_REDIS_URL      Override local backend REDIS_URL
EOF
}

log() {
  printf '
[%s] %s
' "$(date '+%H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

compose() {
  docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
}

cleanup() {
  if [[ -n "$LOCAL_BACKEND_PID" ]] && kill -0 "$LOCAL_BACKEND_PID" >/dev/null 2>&1; then
    log "Stopping local backend (PID $LOCAL_BACKEND_PID)"
    kill "$LOCAL_BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

ensure_corepack_pnpm() {
  require_cmd node
  if command -v pnpm >/dev/null 2>&1; then
    return
  fi
  require_cmd corepack
  log "pnpm not found, enabling it with corepack"
  corepack enable
}

ensure_backend_venv() {
  if [[ "$SKIP_INSTALL" == "1" && -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    return
  fi
  require_cmd uv
  log "Ensuring backend virtualenv with Python 3.11+"
  if [[ ! -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    (cd "$ROOT_DIR/backend" && uv venv --python 3.11 .venv)
  fi
  if [[ "$SKIP_INSTALL" != "1" ]]; then
    log "Installing backend dependencies"
    (cd "$ROOT_DIR/backend" && uv pip install --python .venv/bin/python -r requirements.txt)
  fi
}

write_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    log "Using existing $(basename "$ENV_FILE")"
    return
  fi

  log "Creating $(basename "$ENV_FILE") with local development defaults"
  cat >"$ENV_FILE" <<EOF
POSTGRES_USER=wardrobe
POSTGRES_PASSWORD=wardrobe
POSTGRES_DB=wardrobe
POSTGRES_PORT=5432
REDIS_PORT=6379
BACKEND_PORT=${BACKEND_PORT}
FRONTEND_PORT=3000
NEXTAUTH_URL=http://localhost:3000
SECRET_KEY=change-me-in-production
NEXTAUTH_SECRET=change-me-in-production
DEBUG=true
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=not-needed
AI_VISION_MODEL=llava:7b
AI_TEXT_MODEL=gemma3:latest
CORS_ORIGINS=["http://localhost:3000","http://frontend:3000","http://localhost:${TARO_WEB_PORT}","http://127.0.0.1:${TARO_WEB_PORT}"]
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --setup-only) RUN_SETUP_ONLY=1 ;;
      --start-only) RUN_START_ONLY=1 ;;
      --with-next-frontend) START_NEXT_FRONTEND=1 ;;
      --skip-install) SKIP_INSTALL=1 ;;
      --skip-migrations) SKIP_MIGRATIONS=1 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
    shift
  done

  if [[ $RUN_SETUP_ONLY -eq 1 && $RUN_START_ONLY -eq 1 ]]; then
    echo "--setup-only and --start-only cannot be used together" >&2
    exit 1
  fi
}

choose_runtime_mode() {
  if command -v docker >/dev/null 2>&1; then
    USE_DOCKER=1
    log "Docker detected; using docker-compose mode"
  else
    USE_DOCKER=0
    log "Docker not found; using local backend fallback mode"
  fi
}

start_backend_stack_docker() {
  local services=("${BACKEND_SERVICES[@]}")
  if [[ "$START_NEXT_FRONTEND" == "1" ]]; then
    services+=(frontend caddy)
  fi

  log "Starting docker compose services: ${services[*]}"
  compose up -d "${services[@]}"

  if [[ "$SKIP_MIGRATIONS" != "1" ]]; then
    log "Running alembic migrations in Docker"
    compose run --rm backend alembic upgrade head
  fi
}

ensure_local_postgres() {
  require_cmd psql
  require_cmd pg_isready
  if ! pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo "Local PostgreSQL is not accepting connections on localhost:5432" >&2
    exit 1
  fi
  if ! psql -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'wardrobe'" | grep -q 1; then
    log "Creating local PostgreSQL database: wardrobe"
    createdb wardrobe
  fi
}

ensure_local_redis() {
  require_cmd redis-cli
  if ! redis-cli -p 6379 ping >/dev/null 2>&1; then
    echo "Local Redis is not responding on localhost:6379" >&2
    exit 1
  fi
}

start_backend_stack_local() {
  ensure_local_postgres
  ensure_local_redis
  ensure_backend_venv

  if [[ "$SKIP_MIGRATIONS" != "1" ]]; then
    log "Running alembic migrations locally"
    (
      cd "$ROOT_DIR/backend"
      DATABASE_URL="$LOCAL_DATABASE_URL"       REDIS_URL="$LOCAL_REDIS_URL"       DEBUG=true       SECRET_KEY=change-me-in-production       ./.venv/bin/alembic upgrade head
    )
  fi

  log "Starting local backend on http://localhost:${BACKEND_PORT}"
  (
    cd "$ROOT_DIR/backend"
    DATABASE_URL="$LOCAL_DATABASE_URL"     REDIS_URL="$LOCAL_REDIS_URL"     DEBUG=true     SECRET_KEY=change-me-in-production     CORS_ORIGINS="$LOCAL_CORS_ORIGINS_JSON"     ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"       >"$ROOT_DIR/.local-backend.log" 2>&1
  ) &
  LOCAL_BACKEND_PID=$!
  sleep 2
  if ! kill -0 "$LOCAL_BACKEND_PID" >/dev/null 2>&1; then
    echo "Local backend failed to start. See .local-backend.log" >&2
    exit 1
  fi
}

install_miniapp_deps() {
  if [[ "$SKIP_INSTALL" == "1" ]]; then
    log "Skipping miniapp dependency installation"
    return
  fi

  ensure_corepack_pnpm
  log "Installing miniapp dependencies"
  (cd "$ROOT_DIR/miniapp" && pnpm install --frozen-lockfile)
}

run_taro_web() {
  log "Starting Taro H5 dev server on http://localhost:${TARO_WEB_PORT}"
  log "Backend API expected at ${TARO_APP_API_BASE_URL}"
  cd "$ROOT_DIR/miniapp"
  export TARO_WEB_PORT
  export TARO_APP_API_BASE_URL
  pnpm dev:h5
}

main() {
  parse_args "$@"
  write_env_file
  choose_runtime_mode

  if [[ $RUN_START_ONLY -ne 1 ]]; then
    install_miniapp_deps
  fi

  if [[ "$USE_DOCKER" == "1" ]]; then
    start_backend_stack_docker
  else
    start_backend_stack_local
  fi

  if [[ $RUN_SETUP_ONLY -eq 1 ]]; then
    log "Setup complete. Run this script again without --setup-only to start the Taro web app."
    exit 0
  fi

  run_taro_web
}

main "$@"
