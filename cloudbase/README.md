# CloudBase deployment notes

This directory contains minimal container artifacts for deploying the existing FastAPI API and arq worker into Tencent CloudBase / WeChat Cloud Hosting.

## Services

- `api.Dockerfile` runs the FastAPI application as a single HTTP service.
- `worker.Dockerfile` runs the async worker separately for tagging, notifications, stale recovery, and scheduled jobs.

## Required boundaries

CloudBase deployment for this repository intentionally keeps the current backend architecture and avoids a BaaS rewrite.

### Unsupported / out of scope

- Docker Compose is **not** deployed to Cloud Hosting.
- PostgreSQL and Redis are **not** hosted inside Cloud Hosting; they must be external managed services.
- Persistent local paths like `/data/wardrobe` are **not** durable in Cloud Hosting.
- CloudBase MySQL migration is out of scope for this adaptation.

### Operational requirements

- The API service must expose a single HTTP port.
- Item images should use the storage abstraction, not rely on local container persistence.
- The worker service must **not** use scale-to-zero, because background jobs and scheduled work require always-on capacity.
- CloudBase environment variables should provide the database, Redis, JWT secret, storage backend, and WeChat miniapp credentials.

## Suggested environment variables

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `STORAGE_BACKEND=cloudbase`
- `CLOUDBASE_ENV_ID`
- `CLOUDBASE_STORAGE_BUCKET`
- `WECHAT_MINIAPP_APPID`
- `WECHAT_MINIAPP_SECRET`

## Local development

Continue using the existing Docker Compose workflow locally. These CloudBase artifacts are only for the Cloud Hosting deployment path.
