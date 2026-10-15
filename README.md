<p align="center">
  <img src="./frontend/public/logo.svg" alt="wardrowbe" width="120" height="120">
</p>

<h1 align="center">wardrowbe</h1>

<p align="center">
  Put your wardrobe in rows. Snap. Organize. Wear.
</p>
<p align="center">
  <a href="https://claude.ai/code"><img src="https://img.shields.io/badge/Built%20with%20Claude%20Code-D97757?style=for-the-badge&logo=claude&logoColor=white" alt="Built with Claude Code"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#ai-configuration">AI</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/anyesh">
    <img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Google%20Play-Coming%20Soon-34A853?style=for-the-badge&logo=googleplay&logoColor=white" alt="Google Play - Coming Soon">
  &nbsp;
  <a href="https://apps.apple.com/us/app/wardrowbe/id6759947671">
    <img src="https://img.shields.io/badge/App%20Store-0D96F6?style=for-the-badge&logo=appstore&logoColor=white" alt="App Store">
  </a>
</p>

Self-hosted wardrobe management with AI-powered outfit recommendations. Take photos of your clothes, let AI tag them, and get daily outfit suggestions based on weather and occasion.

## Features

- **Photo-based wardrobe** - Upload photos, AI extracts clothing details automatically
- **Smart recommendations** - Outfits matched to weather, occasion, and your preferences
- **Scheduled notifications** - Daily outfit suggestions via ntfy/Mattermost/email
- **Family support** - Manage wardrobes for household members
- **Wear tracking** - History, ratings, and outfit feedback
- **Analytics** - See what you wear, what you don't, color distribution
- **Fully self-hosted** - Your data stays on your hardware
- **Works with any AI** - OpenAI, Ollama, LocalAI, or any OpenAI-compatible API
- **8 languages** - English, Chinese (Simplified & Traditional), Korean, Japanese, French, German, Italian. Pick one in Settings or let it follow your browser; to add or improve a translation, see [Internationalization](CONTRIBUTING.md#internationalization)

## Screenshots

### Wardrobe & Item Details
| Grid View | Item Details & AI Analysis |
|-----------|---------------------------|
| ![Wardrobe](screenshots/last.png) | ![Item Details](screenshots/wardrobe.png) |

### Wash Tracking & Outfit Suggestions
| Wash Tracking | Suggestions |
|---------------|-------------|
| ![Wash Tracking](screenshots/needs-washing.png) | ![Suggest](screenshots/suggest.png) |

### History & Analytics
| History Calendar | Analytics |
|------------------|-----------|
| ![History](screenshots/history.png) | ![Analytics](screenshots/analytics.png) |

### Pairings
| Pairing View | Pairing Modal |
|--------------|---------------|
| ![Pairing](screenshots/pairings.png) | ![Pairing Modal](screenshots/pairings-modal.png) |

## Quick Start

You need Docker with Docker Compose, about 4GB of RAM (with local Ollama models), and an AI service: [Ollama](#using-ollama-recommended-for-self-hosting) for free local AI, or an OpenAI API key. The published images are multi-arch (`linux/amd64` and `linux/arm64`), so it runs on a Raspberry Pi 5 too.

```bash
git clone https://github.com/Anyesh/wardrowbe.git
cd wardrowbe
cp .env.example .env    # then set the AI_* values, see AI Configuration below

docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head

curl http://localhost:8000/api/v1/health    # {"status":"healthy"}
```

Open http://localhost:3000 and click "Login". The default development login needs no password. Before exposing the app beyond your own machine, set `SECRET_KEY` and `NEXTAUTH_SECRET` in `.env` (`openssl rand -hex 32`) and set up [authentication](#authentication).

To build the images from source with hot reload, use the development stack instead (see [CONTRIBUTING.md](CONTRIBUTING.md#local-development)):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## AI Configuration

Wardrowbe works with any OpenAI-compatible API. You need two types of models:
- **Vision model**: Analyzes clothing images to extract colors, patterns, styles
- **Text model**: Generates outfit recommendations and descriptions

### Using Ollama (Recommended for Self-Hosting)

Free, runs locally, no API key needed, works offline. Install [Ollama](https://ollama.ai), pull a multimodal model that handles both images and recommendations, and point `.env` at it:

```bash
ollama pull gemma3:latest    # 3.4GB
```

```env
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=not-needed
AI_VISION_MODEL=gemma3:latest
AI_TEXT_MODEL=gemma3:latest
```

Use `host.docker.internal` instead of `localhost` so Docker containers can reach your host's Ollama.

### Using OpenAI

Get an API key from https://platform.openai.com/api-keys, then:

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-api-key-here
AI_VISION_MODEL=gpt-4o
AI_TEXT_MODEL=gpt-4o
```

<details>
<summary>Other providers and models (LocalAI, other Ollama models)</summary>

**LocalAI**, a self-hosted OpenAI alternative:

```env
AI_BASE_URL=http://localai:8080/v1
AI_API_KEY=not-needed
AI_VISION_MODEL=gpt-4-vision-preview
AI_TEXT_MODEL=gpt-3.5-turbo
```

Some models handle both vision and text (like qwen2-vl, llama3.2-vision), so one model can serve both:

```env
AI_VISION_MODEL=llama3.2-vision:11b
AI_TEXT_MODEL=llama3.2-vision:11b
```

Other Ollama text models that work: `llama3:latest` (good all-around), `qwen2.5:latest` (fast), `mistral:latest` (creative text).

</details>

<details>
<summary>Running without internal AI</summary>

Internal AI is optional. Set `AI_INTERNAL_ENABLED=false` to run the backend with
no internal AI provider at all: it boots and serves without `AI_BASE_URL`,
`AI_API_KEY`, or model names configured, and defers tagging/suggestions/pairings
to an external agent. You can also disable a single capability with
`AI_VISION_ENABLED=false` (auto-tagging) or `AI_TEXT_ENABLED=false`
(suggestions/pairings); unset switches inherit the master. The effective state is
reported at `GET /api/v1/capabilities`. Defaults keep internal AI **on**, so
existing deployments are unaffected.

</details>

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│                   (Next.js + React Query)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                        Backend                               │
│                   (FastAPI + SQLAlchemy)                     │
└──────────┬──────────────┬──────────────────┬────────────────┘
           │              │                  │
    ┌──────▼──────┐ ┌─────▼─────┐    ┌──────▼──────┐
    │  PostgreSQL │ │   Redis   │    │  AI Service │
    │  (Database) │ │ (Job Queue)│   │ (OpenAI/etc)│
    └─────────────┘ └─────┬─────┘    └─────────────┘
                          │
               ┌──────────▼──────────┐
               │   Background Worker │
               │    (arq - AI Jobs)  │
               └─────────────────────┘
```

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, TanStack Query, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, SQLAlchemy (async), Pydantic, Python 3.11+ |
| Database | PostgreSQL 15 |
| Cache/Queue | Redis 7 |
| Background Jobs | arq |
| Authentication | NextAuth.js (supports OIDC, forward-auth, dev credentials) |
| AI | Any OpenAI-compatible API |

## Deployment

### Docker Compose (Production)

See [docker-compose.prod.yml](docker-compose.prod.yml) for production configuration. Like the default stack, it pulls pre-built images from GHCR rather than building on the host.

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Images are tagged `backend-latest` / `frontend-latest`, and each release also publishes `backend-<version>` / `frontend-<version>`. To pin a release, replace the `-latest` tags in the compose file, e.g. `ghcr.io/anyesh/wardrowbe:backend-1.3.0`.

### Kubernetes

See [k8s/](k8s/) for manifests (PostgreSQL and Redis with persistent storage, backend API and worker, frontend, ingress with TLS, network policies). The [k8s README](k8s/README.md#upgrading) has the upgrade steps for a cluster.

### Client IPs behind a reverse proxy

If a reverse proxy sits in front of Wardrowbe, set `TRUSTED_PROXY_COUNT` so sign-in rate limits see each client's address instead of the proxy's.

<details>
<summary>Which value to use, and why</summary>

Sign-in rate limits key on the client's IP. Every proxy that forwards a request appends the address it received it from to `X-Forwarded-For`, and everything to the left of those entries is whatever the client sent, so the backend reads the entry `TRUSTED_PROXY_COUNT` places from the right. The Next.js frontend adds the header only when a request arrives without one, with the address of the connection, and otherwise relays it unchanged, so it does not count.

| Deployment | Proxies that append | `TRUSTED_PROXY_COUNT` |
|------------|--------------------|-----------------------|
| `docker-compose.yml`, browsers on `:3000` | none | `0` (default) |
| `docker-compose.yml` behind Caddy or Traefik, with `:3000` and `:8000` bound to `127.0.0.1` | the proxy | `1` |
| `docker-compose.prod.yml`, nginx reached directly | nginx | `1` (default) |
| `docker-compose.prod.yml` behind Caddy, Traefik or another proxy on `:8080` | that proxy and nginx | `2` |
| Kubernetes with the bundled Traefik ingress | the ingress controller | `1` (configmap) |

Count a CDN or load balancer in front of these only when it appends to the header too. Too low a count is safe, since clients only end up sharing a proxy's address and its limit; too high a count lets anyone choose the IP they are limited under by sending their own header. Clients that can reach the backend without passing through every counted proxy can do the same, and when a request carries fewer entries than the count, the backend falls back to the address of the connection itself.

An entry may carry a port (`203.0.113.7:4711`, `[2001:db8::1]:4711`), and an IPv4-mapped IPv6 address counts as the IPv4 address. A public IPv6 client is limited by its /64, because one host usually holds a whole /64 and could otherwise rotate addresses inside it; private, unique-local and link-local addresses are limited one by one, so containers on a Docker network stay apart.

</details>

### Upgrading

Replace the code first, then migrate inside the new container, so that old code never runs against the migrated database. Until the migration runs, the new backend answers errors without writing anything.

1. Back up the database, and keep the file: a downgrade loses data, and the [identity repair SQL](docs/sign-in-identities.md#repairing-accounts-if-the-migration-ran-while-the-old-backend-was-still-serving) needs the UTC time in its name.

   ```bash
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
     > backup-$(date -u +%Y%m%dT%H%M%SZ).sql
   ```

2. `docker compose pull`
3. `docker compose up -d`, which replaces the backend, the worker and the image worker.
4. `docker compose exec backend alembic upgrade head`

`docker-compose.prod.yml` is a standalone file, so with the production stack every one of these commands takes `-f docker-compose.prod.yml`. Sign-in tokens issued before the upgrade keep working until they expire (7 days).

Upgrading from a release before sign-in identities (the `user_identities` table)? [Sign-in identities](docs/sign-in-identities.md#upgrading-to-sign-in-identities) covers what the migration changes, how to repair accounts if it ran while the old backend was still serving, and how to downgrade.

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis URL for the API and workers (default: `redis://localhost:6379/0`; the bundled Compose files set it themselves) | No |
| `SECRET_KEY` | Backend secret for JWT. The backend refuses to start with the default `change-me-in-production` unless `DEBUG=true` and neither OIDC nor forward-auth is configured | Yes |
| `NEXTAUTH_SECRET` | NextAuth session encryption. The frontend refuses to start with a value beginning `change-me-in-production` when `OIDC_ISSUER_URL` or `FORWARD_AUTH_SECRET` is set | Yes |
| `AI_BASE_URL` | AI service URL | Yes |
| `AI_API_KEY` | AI API key (if required) | Depends |
| `APP_URL` | Public app URL used in notification and invite links (default: `http://localhost:3000`) | No |
| `LOG_LEVEL` | Log level for the API and workers (default: INFO) | No |

<details>
<summary>Sign-in and reverse proxy</summary>

| Variable | Description | Required |
|----------|-------------|----------|
| `OIDC_ISSUER_URL` | OIDC provider URL (enables SSO login) | No |
| `OIDC_CLIENT_ID` | OIDC client ID | If OIDC |
| `OIDC_CLIENT_SECRET` | OIDC client secret | If OIDC |
| `OIDC_CA_BUNDLE` | Path inside the backend container to a PEM CA certificate the backend trusts for the OIDC provider (private CA or self-signed certs) | No |
| `NODE_EXTRA_CA_CERTS` | Path inside the frontend container to a PEM CA certificate Node trusts on top of the system store, for the OIDC provider and an `https` `BACKEND_URL` | No |
| `LOCAL_DNS` | Custom DNS server for container name resolution (e.g. local OIDC host) | No |
| `FORWARD_AUTH_SECRET` | Shared secret the forward-auth proxy sends as `X-Forward-Auth-Secret` (at least 32 characters; enables forward-auth). Set the same value for the backend and the frontend | No |
| `TINYAUTH_URL` | TinyAuth base URL, where logout sends the browser in forward-auth mode | No |
| `FORWARD_AUTH_LOGOUT_URL` | Proxy logout URL for Authelia and others in forward-auth mode | No |
| `TRUSTED_PROXY_COUNT` | Reverse proxies in front of the API that append to `X-Forwarded-For` (default: 0; `docker-compose.prod.yml` and k8s set 1). See [Client IPs behind a reverse proxy](#client-ips-behind-a-reverse-proxy) | No |

</details>

<details>
<summary>Notifications</summary>

| Variable | Description | Required |
|----------|-------------|----------|
| `NTFY_SERVER` | Default ntfy server offered when a user adds an ntfy channel | No |
| `NTFY_TOKEN` | Access token for `NTFY_SERVER`, used for any ntfy channel on that server that has no token of its own | No |
| `SMTP_HOST` | SMTP server for email notifications | No |
| `SMTP_PORT` | SMTP port (default: 587) | No |
| `SMTP_USER` | SMTP username | No |
| `SMTP_PASSWORD` | SMTP password | No |
| `SMTP_USE_TLS` | Use STARTTLS for SMTP (default: true) | No |
| `SMTP_FROM_NAME` | Sender name on notification emails (default: Wardrowbe) | No |
| `SMTP_FROM_EMAIL` | Sender address (default: `SMTP_USER`) | No |

</details>

<details>
<summary>Background removal, location and container user</summary>

| Variable | Description | Required |
|----------|-------------|----------|
| `BG_REMOVAL_PROVIDER` | Background removal backend: `rembg` or `http` (default: `rembg`) | No |
| `BG_REMOVAL_MODEL` | rembg model name (default: `birefnet-general-lite`) | No |
| `BG_REMOVAL_URL` | URL for HTTP bg removal provider | If http |
| `BG_REMOVAL_API_KEY` | API key for HTTP bg removal provider | No |
| `NEXT_PUBLIC_ENABLE_IP_LOCATION_FALLBACK` | Enable IP-based approximate location when browser geolocation is denied/unavailable. Off by default (sends the user's IP to a third party). Set to `true` to enable | No |
| `NEXT_PUBLIC_NETWORK_LOCATION_URL` | Override the IP geolocation provider (default: `https://ipapi.co/json/`). Only used when the fallback above is enabled | No |
| `PUID` | Uid the app process runs as (default: 1000 backend/worker, 1001 frontend) | No |
| `PGID` | Gid the app process runs as (default: 1000 backend/worker, 1001 frontend) | No |

</details>

<details>
<summary>Using your own Redis (password, TLS, unix socket)</summary>

Set the same `REDIS_URL` on the API and both workers. The bundled Compose files point every service at their own Redis container, so a `REDIS_URL` in `.env` has no effect there.

- Password: `redis://:password@redis:6379/2` (or `user:password@`)
- TLS: `rediss://:password@redis:6380/2`
- Unix socket: `unix://:password@/run/redis/redis.sock?db=2`

`db` is the only supported query parameter. Percent-encode reserved characters in passwords and socket paths (`@` as `%40`, `/` as `%2F`, `#` as `%23`).

</details>

See [.env.example](.env.example) for all options.

### Authentication

- **Development Mode** (default): Simple email/name login, no setup required
- **OIDC Mode**: Any OIDC provider (PocketID, Authentik, Keycloak, Auth0, etc.)
- **Forward-auth Mode**: An authenticating reverse proxy such as TinyAuth or Authelia signs people in. Setup, proxy snippets and the security notes are in [docs/forward-auth.md](docs/forward-auth.md)

To enable OIDC, set `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` in your `.env`, and register `{NEXTAUTH_URL}/api/auth/callback/oidc` as the callback/redirect URI in your provider (e.g. `http://localhost:8080/api/auth/callback/oidc`).

<details>
<summary>OIDC provider with a self-signed certificate or private CA</summary>

Mount that CA certificate (PEM) into the backend container and set `OIDC_CA_BUNDLE` to its path inside the container, e.g. `/certs/internal-ca.pem`. The backend then verifies the provider's discovery and JWKS requests against that CA; TLS verification itself is never turned off. The frontend talks to the provider too (NextAuth fetches the discovery document and JWKS, exchanges the code at the token endpoint and reads the userinfo endpoint), so mount the same PEM into the frontend container and set `NODE_EXTRA_CA_CERTS` to its path there; it also covers a `BACKEND_URL` served over `https` by the same CA. The certificate has to be readable by the uid and gid the containers run as (`PUID`/`PGID`), for example:

```yaml
services:
  backend:
    environment:
      OIDC_CA_BUNDLE: /certs/internal-ca.pem
    volumes:
      - ./certs:/certs:ro
  frontend:
    environment:
      NODE_EXTRA_CA_CERTS: /certs/internal-ca.pem
    volumes:
      - ./certs:/certs:ro
```

</details>

<details>
<summary>OIDC provider on a hostname containers can't resolve</summary>

If your OIDC provider runs on a hostname that Docker containers can't resolve (e.g. a local DNS name), set `LOCAL_DNS` to your DNS server IP, or set `OIDC_HOST` and `OIDC_HOST_IP` to inject the hostname directly into the container's `/etc/hosts`.

</details>

An account can sign in through more than one provider. To block a person or unlink one of their sign-ins, see [Sign-in identities](docs/sign-in-identities.md#accounts-and-sign-in-identities).

### Notifications

Users add their own channels in the app: **ntfy** push notifications, **Mattermost** webhooks, or **email** (set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` in `.env`).

### Weather and location

Weather comes from [Open-Meteo](https://open-meteo.com/), free with no API key. The Settings page fills in your coordinates from the browser's Geolocation API, and a location name you type is geocoded with OpenStreetMap Nominatim.

<details>
<summary>Approximate location from the IP address (off by default)</summary>

If browser geolocation is denied or unavailable, an optional fallback can approximate your location from your IP address via a third-party service (`ipapi.co` by default). It is disabled by default because it sends the user's IP to an external provider; enable it with `NEXT_PUBLIC_ENABLE_IP_LOCATION_FALLBACK=true` and optionally point `NEXT_PUBLIC_NETWORK_LOCATION_URL` at a provider you trust. These are build-time frontend variables, so set them before building the frontend image.

</details>

### Background Removal

Works out of the box: the backend image ships rembg with the default `birefnet-general-lite` model already downloaded. It is more accurate on clothes than `u2net`, and the cut-out is cleaned afterwards: small holes the model punched into a print are filled back in, loose bits of background are dropped, and a result that lost the garment entirely keeps the original photo.

<details>
<summary>Other rembg models, or an HTTP provider</summary>

Change the rembg model with `BG_REMOVAL_MODEL` (options: `u2net`, `isnet-general-use`, `silueta`, `u2netp`). A non-default model is downloaded the first time background removal runs, so that first run needs internet access; the compose files keep it in the `rembg_models` volume so later runs work offline. On Kubernetes, mount a PersistentVolume at `/opt/rembg/models` on the image-worker if you change the model, or it is downloaded again on every pod start. The volume must be writable by uid 1000: the manifests' `fsGroup` covers a PersistentVolumeClaim, but a `hostPath` volume needs its directory owned by that uid. The worker links the baked `birefnet-general-lite` into the volume on start, so switching back needs no download.

To use an HTTP provider (e.g. [withoutbg](https://github.com/nicholasgasior/withoutbg)) instead:

```env
BG_REMOVAL_PROVIDER=http
BG_REMOVAL_URL=http://withoutbg:5000
BG_REMOVAL_API_KEY=          # optional
```

If neither is configured, the remove-background button returns a 501 with setup instructions.

</details>

## Troubleshooting

Start with `docker compose ps` and `docker compose logs backend worker frontend --tail=50`; most problems show up there.

<details>
<summary>Frontend shows "500 Internal Server Error" or won't load</summary>

```bash
# 1. Check all services are healthy
docker compose ps

# 2. Check backend is responding
curl http://localhost:8000/api/v1/health

# 3. Verify migrations ran successfully
docker compose exec backend alembic current

# 4. Check logs for errors
docker compose logs backend frontend --tail=50

# 5. If migrations failed, run them manually
docker compose exec backend alembic upgrade head
```

</details>

<details>
<summary>AI features not working / images not being analyzed</summary>

```bash
# For Ollama users:
# 1. Verify Ollama is running and accessible
curl http://localhost:11434/api/tags
# Should show your installed models

# 2. Check you have the vision model
ollama list | grep gemma

# 3. Verify .env has correct configuration
cat .env | grep AI_

# 4. Check worker logs for AI errors
docker compose logs worker --tail=50

# For OpenAI users:
# 1. Verify API key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $AI_API_KEY"

# 2. Check you have credits remaining in your account
```

</details>

<details>
<summary>Port already in use</summary>

```bash
# Check what's using the ports
sudo lsof -i :3000  # Frontend
sudo lsof -i :8000  # Backend
sudo lsof -i :5432  # PostgreSQL
sudo lsof -i :6379  # Redis

# Stop conflicting services or change ports in .env
```

</details>

<details>
<summary>Database migration errors</summary>

```bash
# Check current migration version
docker compose exec backend alembic current

# View migration history
docker compose exec backend alembic history

# If migrations are corrupted, reset (WARNING: Deletes all data!)
docker compose down -v
docker compose up -d
sleep 10
docker compose exec backend alembic upgrade head
```

</details>

<details>
<summary>Container keeps restarting, or the app is slow</summary>

```bash
# Check container logs
docker compose logs <service-name> --tail=100

# Common issues:
# - Database not ready: Wait 30 seconds and retry
# - Out of memory: Increase Docker memory limit
# - Permission errors: Check file permissions on volumes

# Check resource usage
docker stats

# If AI analysis is slow:
# - For Ollama: Use smaller quantized models
# - For OpenAI: Check your rate limits
```

</details>

Still stuck? Check the [issues](https://github.com/Anyesh/wardrowbe/issues) and [discussions](https://github.com/Anyesh/wardrowbe/discussions), or open a new issue with the output of `docker compose ps`, the relevant logs, your `.env` with secrets redacted, and the steps to reproduce.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, the development setup and how to run the tests. The API docs are served at http://localhost:8000/docs and http://localhost:8000/redoc in dev mode (`DEBUG=true` with neither OIDC nor forward-auth configured).

## Support

If you find wardrowbe useful, consider supporting its development:

<a href="https://buymeacoffee.com/anyesh"><img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee"></a>

Thanks to our supporters:

- [@aaratisharma-star](https://github.com/aaratisharma-star)
- [@zkhcohen](https://github.com/zkhcohen)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
