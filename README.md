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
  <a href="#languages">Languages</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#architecture">Architecture</a> •
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
- **8 languages** - English, Chinese (Simplified & Traditional), Korean, Japanese, French, German, Italian

## Languages

Wardrowbe's UI is fully translated into 8 languages via `next-intl`. Pick a language from Settings, or let it follow your browser automatically.

| Language | Locale code |
|----------|-------------|
| English | `en` |
| 中文简体 (Chinese, Simplified) | `zh-CN` |
| 中文繁體 (Chinese, Traditional) | `zh-TW` |
| 한국어 (Korean) | `ko` |
| 日本語 (Japanese) | `ja` |
| Français (French) | `fr` |
| Deutsch (German) | `de` |
| Italiano (Italian) | `it` |

Want to add a language or improve a translation? See [Internationalization](CONTRIBUTING.md#internationalization) in the contributing guide.

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

### Prerequisites

- Docker and Docker Compose installed
- At least 4GB of RAM available
- An AI service (Ollama recommended for free local AI, or OpenAI API key)

### Setup

#### Step 1: Install Ollama (if using local AI)

**Option A: Using Ollama (Recommended - Free, runs locally)**

```bash
# Install Ollama from https://ollama.ai
# Then pull required models:
ollama pull gemma3        # Multimodel LLM (for image analysis and outfit recommendations)

# Verify it's running:
curl http://localhost:11434/api/tags
```

**Option B: Using OpenAI (Paid API)**

Get your API key from https://platform.openai.com/api-keys

#### Step 2: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/yourusername/wardrowbe.git
cd wardrowbe

# Copy environment template
cp .env.example .env

# IMPORTANT: Edit .env and configure AI settings
# For Ollama (default in .env.example):
#   AI_BASE_URL=http://host.docker.internal:11434/v1
#   AI_VISION_MODEL=gemma3:latest
#   AI_TEXT_MODEL=gemma3:latest
#
# For OpenAI, uncomment and set:
#   AI_BASE_URL=https://api.openai.com/v1
#   AI_API_KEY=sk-your-api-key-here
#   AI_VISION_MODEL=gpt-4o
#   AI_TEXT_MODEL=gpt-4o

# Optional: Generate secure secrets for production
# SECRET_KEY=$(openssl rand -hex 32)
# NEXTAUTH_SECRET=$(openssl rand -hex 32)
```

#### Step 3: Start Services

`docker-compose.yml` pulls pre-built multi-arch images (`linux/amd64` and `linux/arm64`, so Raspberry Pi and other ARM hosts work) from GitHub Container Registry. No local build tooling is required on the host.

```bash
# Pull the latest published images, then start all containers
docker compose pull
docker compose up -d

# Wait for services to be healthy (30 seconds)
docker compose ps

# Run database migrations (REQUIRED)
docker compose exec backend alembic upgrade head

# Verify everything is working
curl http://localhost:8000/api/v1/health
# Should return: {"status":"healthy"}
```

To build the images from source instead of pulling them, use the development stack below (`docker-compose.dev.yml`), which builds locally and enables hot reload.

#### Step 4: Access the App

- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs (dev mode only)
- **Login:** Click "Login" - uses dev credentials by default (no password needed)

### Development Mode

For hot reloading during development (auto-rebuilds on code changes):

```bash
# Start in dev mode
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run migrations (first time only)
docker compose exec backend alembic upgrade head

# View logs
docker compose logs -f frontend backend
```

## AI Configuration

Wardrowbe works with any OpenAI-compatible API. You need two types of models:
- **Vision model**: Analyzes clothing images to extract colors, patterns, styles
- **Text model**: Generates outfit recommendations and descriptions

### Running without internal AI

Internal AI is optional. Set `AI_INTERNAL_ENABLED=false` to run the backend with
no internal AI provider at all — it boots and serves without `AI_BASE_URL`,
`AI_API_KEY`, or model names configured, and defers tagging/suggestions/pairings
to an external agent. You can also disable a single capability with
`AI_VISION_ENABLED=false` (auto-tagging) or `AI_TEXT_ENABLED=false`
(suggestions/pairings); unset switches inherit the master. The effective state is
reported at `GET /api/v1/capabilities`. Defaults keep internal AI **on**, so
existing deployments are unaffected.

### Using Ollama (Recommended for Self-Hosting)

**Free, runs locally, no API key needed, works offline**

1. Install [Ollama](https://ollama.ai)
2. Pull models:
   ```bash
   ollama pull gemma3:latest  # multimodel LLM (3.4GB) - analyze images and generates recommendations

   # Alternative text models you can use:
   # ollama pull llama3:latest     # Good all-around model
   # ollama pull qwen2.5:latest    # Fast and efficient
   # ollama pull mistral:latest    # Great for creative text
   ```

3. Configure in `.env`:
   ```env
   AI_BASE_URL=http://host.docker.internal:11434/v1
   AI_API_KEY=not-needed
   AI_VISION_MODEL=gemma3:latest
   AI_TEXT_MODEL=gemma3:latest
   ```

**Note:** Use `host.docker.internal` instead of `localhost` so Docker containers can reach your host's Ollama.

### Using OpenAI

**Paid API, requires internet connection**

1. Get API key from https://platform.openai.com/api-keys
2. Configure in `.env`:
   ```env
   AI_BASE_URL=https://api.openai.com/v1
   AI_API_KEY=sk-your-api-key-here
   AI_VISION_MODEL=gpt-4o
   AI_TEXT_MODEL=gpt-4o
   ```

### Using LocalAI

**Self-hosted OpenAI alternative**

```env
AI_BASE_URL=http://localai:8080/v1
AI_API_KEY=not-needed
AI_VISION_MODEL=gpt-4-vision-preview
AI_TEXT_MODEL=gpt-3.5-turbo
```

### Using Multimodal Models

Some models can handle both vision and text (like qwen2-vl, llama3.2-vision):

```env
AI_VISION_MODEL=llama3.2-vision:11b
AI_TEXT_MODEL=llama3.2-vision:11b  # Same model for both tasks
```

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

### Tech Stack

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

Images are tagged `backend-latest` / `frontend-latest`, and each release also
publishes `backend-<version>` / `frontend-<version>` (e.g. `backend-1.3.0`). To
pin a deployment to a specific release, replace the `-latest` tags in the
compose file with the version, e.g. `ghcr.io/anyesh/wardrowbe:backend-1.3.0`.

### Client IPs behind a reverse proxy

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

### Kubernetes

See the [k8s/](k8s/) directory for Kubernetes manifests including:
- PostgreSQL and Redis with persistent storage
- Backend API and worker deployments
- Next.js frontend
- Ingress with TLS
- Network policies

The [k8s README](k8s/README.md#upgrading) has the upgrade steps for a cluster.

### Upgrading

Replace the code first, then migrate inside the new container, so that old code never runs against the migrated database. Until the migration runs, the new backend answers errors without writing anything.

1. Back up the database. A downgrade loses data (see below), so keep this file; the UTC time in its name is also the time the repair SQL further down needs.

   ```bash
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
     > backup-$(date -u +%Y%m%dT%H%M%SZ).sql
   ```

2. `docker compose pull`
3. `docker compose up -d`, which replaces the backend, the worker and the image worker.
4. `docker compose exec backend alembic upgrade head`

`docker-compose.prod.yml` is a standalone file, so with the production stack every one of these commands takes `-f docker-compose.prod.yml`.

Sign-in tokens issued before the upgrade keep working until they expire (7 days).

#### Upgrading to sign-in identities

This release keeps each user's sign-ins in a new `user_identities` table, one identity per provider, so signing in through a second provider no longer ends the first provider's sessions. The migration copies every user's existing sign-in into it.

If the migration ran while the old backend was still serving (the steps above were not followed), two things can go wrong:

- Users the old backend created after the migration have no identity, so they can sign in only through a verified email address. An unverified one gets a conflict error, and a verified sign-in claiming the same address takes the address over and detaches the old account.
- Accounts the old backend linked to a new sign-in by email keep accepting the previous sign-in too.

This SQL repairs the accounts that existed before the backup, including one whose previous sign-in the new backend has already accepted since, and gives an identity to every account the old backend created without one. It holds sign-ins back until it commits. If another account still holds a sign-in it needs to restore, it changes nothing and names the accounts it could not repair; unlink the conflicting identity by hand (below) and run it again. Any other account the old backend linked to a new sign-in by email during the overlap (one created between the backup and the migration, or one the new backend created or linked) keeps the sign-ins it holds; the one the old backend linked gets the account back by signing in again with the same verified email, and an identity that should lose access has to be unlinked by hand (below). Take the backup right before upgrading to keep that window short. Replace `<backup time>` with the time from the backup's file name, written as `2026-10-11T09:30:00`:

```sql
BEGIN;
LOCK TABLE users, user_identities IN EXCLUSIVE MODE;
-- Rows the migration copied keep the created_at of a user that existed before the backup; those
-- are the rows the old backend can have left stale by moving external_id.
CREATE TEMP TABLE stale ON COMMIT DROP AS
SELECT i.id, i.user_id FROM user_identities i JOIN users u ON u.id = i.user_id
WHERE i.provider IN ('legacy', 'oidc', 'dev') AND i.created_at = u.created_at
  AND u.created_at < TIMESTAMPTZ '<backup time>Z'
  AND u.external_id IS NOT NULL AND i.subject <> u.external_id;
CREATE TEMP TABLE targets ON COMMIT DROP AS
SELECT u.id FROM users u
WHERE u.external_id IS NOT NULL
  AND (
    u.id IN (SELECT user_id FROM stale)
    OR (
      u.created_at >= TIMESTAMPTZ '<backup time>Z'
      AND NOT EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = u.id)
    )
  );
DELETE FROM user_identities WHERE id IN (SELECT id FROM stale);
INSERT INTO user_identities (id, user_id, provider, subject, created_at)
SELECT gen_random_uuid(), u.id, 'legacy', u.external_id, u.created_at
FROM users u WHERE u.id IN (SELECT id FROM targets)
ON CONFLICT DO NOTHING;
DO $$
DECLARE skipped text;
BEGIN
  SELECT string_agg(u.email, ', ') INTO skipped FROM users u
  WHERE u.id IN (SELECT id FROM targets)
    AND (
      NOT EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = u.id
        AND i.subject = u.external_id AND i.provider IN ('legacy', 'oidc', 'dev'))
      OR EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id <> u.id
        AND i.subject = u.external_id AND i.provider IN ('legacy', 'oidc', 'dev'))
    );
  IF skipped IS NOT NULL THEN
    RAISE EXCEPTION 'Nothing was changed. Another account holds the sign-in of: %', skipped;
  END IF;
END $$;
COMMIT;
```

Downgrading below this migration keeps one sign-in per account (OIDC first, then development login, then the pre-upgrade one) and gives an account that loses every candidate a placeholder no sign-in matches. Forward-auth sign-ins are never kept, so an account whose only sign-in is forward-auth gets a placeholder. On the old version a verified sign-in whose email matches a placeholder account's verified email is linked to that account, while a matching unverified email moves to a new account and leaves the placeholder account's data behind. Every token issued after the upgrade stops working. Restore the backup instead where you can. To downgrade anyway, stop the backend and workers first, because the new backend answers every signed-in request with an error once the table is gone, and run the downgrade with the new image, since only it contains this migration:

```bash
docker compose stop backend worker image-worker
docker compose run --rm --no-deps backend alembic downgrade 6c1e8f2a9d47
```

Then point the image tags at the previous release and run `docker compose up -d`.

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `SECRET_KEY` | Backend secret for JWT. The backend refuses to start with the default `change-me-in-production` unless `DEBUG=true` and neither OIDC nor forward-auth is configured | Yes |
| `PUID` | Uid the app process runs as (default: 1000 backend/worker, 1001 frontend) | No |
| `PGID` | Gid the app process runs as (default: 1000 backend/worker, 1001 frontend) | No |
| `NEXTAUTH_SECRET` | NextAuth session encryption. The frontend refuses to start with a value beginning `change-me-in-production` when `OIDC_ISSUER_URL` or `FORWARD_AUTH_SECRET` is set | Yes |
| `AI_BASE_URL` | AI service URL | Yes |
| `AI_API_KEY` | AI API key (if required) | Depends |
| `OIDC_ISSUER_URL` | OIDC provider URL (enables SSO login) | No |
| `OIDC_CLIENT_ID` | OIDC client ID | If OIDC |
| `OIDC_CLIENT_SECRET` | OIDC client secret | If OIDC |
| `OIDC_CA_BUNDLE` | Path inside the backend container to a PEM CA certificate the backend trusts for the OIDC provider (private CA or self-signed certs) | No |
| `NODE_EXTRA_CA_CERTS` | Path inside the frontend container to a PEM CA certificate Node trusts on top of the system store, for the OIDC provider and an `https` `BACKEND_URL` | No |
| `FORWARD_AUTH_SECRET` | Shared secret the forward-auth proxy sends as `X-Forward-Auth-Secret` (at least 32 characters; enables forward-auth). Set the same value for the backend and the frontend | No |
| `TINYAUTH_URL` | TinyAuth base URL, where logout sends the browser in forward-auth mode | No |
| `FORWARD_AUTH_LOGOUT_URL` | Proxy logout URL for Authelia and others in forward-auth mode | No |
| `TRUSTED_PROXY_COUNT` | Reverse proxies in front of the API that append to `X-Forwarded-For` (default: 0; `docker-compose.prod.yml` and k8s set 1). See [Client IPs behind a reverse proxy](#client-ips-behind-a-reverse-proxy) | No |
| `NTFY_SERVER` | Default ntfy server offered when a user adds an ntfy channel | No |
| `NTFY_TOKEN` | Access token for `NTFY_SERVER`, used for any ntfy channel on that server that has no token of its own | No |
| `LOCAL_DNS` | Custom DNS server for container name resolution (e.g. local OIDC host) | No |
| `SMTP_HOST` | SMTP server for email notifications | No |
| `SMTP_PORT` | SMTP port (default: 587) | No |
| `SMTP_USER` | SMTP username | No |
| `SMTP_PASSWORD` | SMTP password | No |
| `SMTP_USE_TLS` | Use STARTTLS for SMTP (default: true) | No |
| `SMTP_FROM_NAME` | Sender name on notification emails (default: Wardrowbe) | No |
| `SMTP_FROM_EMAIL` | Sender address (default: `SMTP_USER`) | No |
| `APP_URL` | Public app URL used in notification and invite links (default: `http://localhost:3000`) | No |
| `LOG_LEVEL` | Log level for the API and workers (default: INFO) | No |
| `BG_REMOVAL_PROVIDER` | Background removal backend: `rembg` or `http` (default: `rembg`) | No |
| `BG_REMOVAL_MODEL` | rembg model name (default: `u2net`) | No |
| `BG_REMOVAL_URL` | URL for HTTP bg removal provider | If http |
| `BG_REMOVAL_API_KEY` | API key for HTTP bg removal provider | No |
| `NEXT_PUBLIC_ENABLE_IP_LOCATION_FALLBACK` | Enable IP-based approximate location when browser geolocation is denied/unavailable. Off by default (sends the user's IP to a third party). Set to `true` to enable | No |
| `NEXT_PUBLIC_NETWORK_LOCATION_URL` | Override the IP geolocation provider (default: `https://ipapi.co/json/`). Only used when the fallback above is enabled | No |

See [.env.example](.env.example) for all options.

### Location Detection (Privacy Note)

The Settings page can fill in your coordinates from the browser's Geolocation API. If that is denied or unavailable, an optional fallback can approximate your location from your IP address via a third-party service (`ipapi.co` by default). This fallback is **disabled by default** because it sends the user's IP to an external provider; enable it with `NEXT_PUBLIC_ENABLE_IP_LOCATION_FALLBACK=true` and optionally point `NEXT_PUBLIC_NETWORK_LOCATION_URL` at a provider you trust. These are build-time frontend variables, so set them before building the frontend image. Geocoding a location name you type yourself still uses OpenStreetMap Nominatim regardless of this setting.

### Background Removal (Optional)

Remove image backgrounds from wardrobe items. Two backends supported:

**rembg (local, default):**

No config needed, since the backend image ships rembg with the default `u2net` model already downloaded. Change model with `BG_REMOVAL_MODEL` (options: `isnet-general-use`, `silueta`, `u2netp`). A non-default model is downloaded the first time background removal runs, so that first run needs internet access; the compose files keep it in the `rembg_models` volume so later runs work offline. On Kubernetes, mount a PersistentVolume at `/opt/rembg/models` on the image-worker if you change the model, or it is downloaded again on every pod start.

**HTTP provider (e.g. [withoutbg](https://github.com/nicholasgasior/withoutbg)):**
```env
BG_REMOVAL_PROVIDER=http
BG_REMOVAL_URL=http://withoutbg:5000
BG_REMOVAL_API_KEY=          # optional
```

If neither is configured, the remove-background button returns a 501 with setup instructions.

### Authentication

- **Development Mode** (default): Simple email/name login, no setup required
- **OIDC Mode**: Any OIDC provider (PocketID, Authentik, Keycloak, Auth0, etc.)
- **Forward-auth Mode**: An authenticating reverse proxy such as TinyAuth or Authelia signs people in (see [Forward-auth](#forward-auth-tinyauth-authelia))

To enable OIDC, set `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` in your `.env`. If your OIDC provider uses a self-signed certificate or a private CA, mount that CA certificate (PEM) into the backend container and set `OIDC_CA_BUNDLE` to its path inside the container, e.g. `/certs/internal-ca.pem`. The backend then verifies the provider's discovery and JWKS requests against that CA; TLS verification itself is never turned off. The frontend talks to the provider too (NextAuth fetches the discovery document and JWKS, exchanges the code at the token endpoint and reads the userinfo endpoint), so mount the same PEM into the frontend container and set `NODE_EXTRA_CA_CERTS` to its path there; it also covers a `BACKEND_URL` served over `https` by the same CA. The certificate has to be readable by the uid and gid the containers run as (`PUID`/`PGID`), for example:

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

If your OIDC provider runs on a hostname that Docker containers can't resolve (e.g. a local DNS name), set `LOCAL_DNS` to your DNS server IP, or set `OIDC_HOST` and `OIDC_HOST_IP` to inject the hostname directly into the container's `/etc/hosts`.

When registering the app in your OIDC provider, use this as the callback/redirect URI:

```
{NEXTAUTH_URL}/api/auth/callback/oidc
```

For example, if `NEXTAUTH_URL=http://localhost:8080`, the callback URL is:

```
http://localhost:8080/api/auth/callback/oidc
```

#### Accounts and sign-in identities

An account holds at most one sign-in identity per provider (development login, OIDC, forward-auth). A new identity whose verified email belongs to an existing account with a verified email joins that account, and its sessions sit alongside the sessions of the account's other providers. A second identity from the same provider replaces the first, so two OIDC subjects, or two proxy usernames, that share an email address take turns holding the account and each sign-in ends the other's sessions.

To block a person, deactivate their account. Every request their tokens make is refused from then on. If the account's email is unverified, a sign-in whose provider verifies that address still gets a new account with it, so check `email_verified` too:

```sql
UPDATE users SET is_active = false WHERE email = 'person@example.com';
```

To unlink one sign-in identity and end its sessions, find the identity's id with `SELECT id, provider, subject FROM user_identities WHERE user_id = '<user id>';` and run the transaction below with it. It deletes the identity and clears the account's pre-upgrade sign-in when that names the identity (a forward-auth identity never does, even when a kept `legacy` identity has the same subject) or when the account keeps no other identity, so a later downgrade cannot hand the account back to an old sign-in. The id stays the same when a pre-upgrade (`legacy`) sign-in is used again after you listed it. The `DELETE` must report one row; zero means another sign-in replaced the identity in the meantime, so list the identities again.

```sql
BEGIN;
LOCK TABLE users, user_identities IN EXCLUSIVE MODE;
UPDATE users u SET external_id = NULL
FROM user_identities i
WHERE i.id = '<identity id>' AND u.id = i.user_id
  AND (
    (u.external_id = i.subject AND i.provider <> 'forward_auth')
    OR NOT EXISTS (SELECT 1 FROM user_identities o WHERE o.user_id = u.id AND o.id <> i.id)
  );
DELETE FROM user_identities WHERE id = '<identity id>';
COMMIT;
```

Unlinking does not block the person: while the account's email is verified, any later sign-in whose provider verifies that same address joins the account again. Deactivate the account for that.

### Forward-auth (TinyAuth, Authelia)

Forward-auth lets an authenticating reverse proxy sign people in to Wardrowbe. It works like this:

1. The proxy (TinyAuth or Authelia behind Caddy, Traefik or nginx) authenticates the browser and adds `Remote-User`, `Remote-Email`, optionally `Remote-Name`, and a static `X-Forward-Auth-Secret` header to every request it forwards.
2. On `/login` the app signs in by itself: the backend checks the secret, then signs in the forward-auth identity named by `Remote-User`, creating an account for it when no account matches (see [Accounts and sign-in identities](#accounts-and-sign-in-identities)). A wrong secret is refused, and `Remote-*` headers sent without the secret are ignored.
3. After sign-in, requests use Wardrowbe's own session token, and the proxy headers never sign a request in. They can only refuse one: a request that carries the right secret and a `Remote-User` that is not a forward-auth identity of the session's account gets a 401. Image links the app already handed out are signed and keep working until they expire. So if the proxy starts reporting a different `Remote-User`, the next page load signs the old session out, and a tab that is already open has its API calls refused until it reloads (unless those calls skip the proxy, see the mobile app below). A page load also signs out a forward-auth session that reaches the app without the secret or without `Remote-User`, and an OIDC or development session in a browser the proxy now serves, since the login page offers only forward-auth there.
4. Logging out ends the Wardrowbe session, then sends the browser to the proxy's logout page so the proxy session ends too (TinyAuth's page asks for one more click).

Set these in `.env`:

```env
# At least 32 random visible ASCII characters and no spaces, e.g. the output of: openssl rand -hex 32.
# The backend and the frontend both read it, and the compose files pass it to both.
FORWARD_AUTH_SECRET=
# The public URL the proxy serves
NEXTAUTH_URL=https://wardrobe.example.com
# Where logout sends the browser. TinyAuth: set its base URL.
TINYAUTH_URL=https://tinyauth.example.com
# Authelia and other proxies: set the full logout URL instead. It is used as is,
# so include the return address (Authelia's parameter is rd).
# FORWARD_AUTH_LOGOUT_URL=https://auth.example.com/logout?rd=https%3A%2F%2Fwardrobe.example.com%2Flogin%3FloggedOut%3D1
```

Authelia only follows `rd` to an HTTPS address inside one of its session cookie domains; otherwise it stays on its own portal after logging out.

If only one of the two services gets the secret, sign-in fails. With only the backend's, the login page reports missing proxy headers and the frontend log says its `FORWARD_AUTH_SECRET` is not set. With only the frontend's, the login page offers OIDC or development sign-in, and every page load through the proxy signs that session out again, with a warning in the frontend log.

Put the proxy in front of the frontend on `:3000` with the default `docker-compose.yml`, or in front of nginx on `:8080` with `docker-compose.prod.yml`. Only the proxy should be able to reach those ports. The prod compose already binds nginx to `127.0.0.1` and publishes nothing else; with the default compose, set `FRONTEND_PORT=127.0.0.1:3000` and `BACKEND_PORT=127.0.0.1:8000` in `.env` (or remove the `ports:` entries if the proxy shares the stack's Docker network), so nobody on your LAN can skip the proxy or watch the secret go past in plain HTTP.

Then set `TRUSTED_PROXY_COUNT` to `1` with the default compose or `2` with the prod compose, so sign-in rate limits see each browser's address instead of the proxy's (see [Client IPs behind a reverse proxy](#client-ips-behind-a-reverse-proxy)).

Every snippet below strips any `Remote-*` and `X-Forward-Auth-Secret` headers the client sent before the auth server's headers are set, and adds the secret on the way to Wardrowbe. Keep both steps if you adapt them to another proxy.

**Caddy + TinyAuth**, both on the stack's Docker network (with the prod compose, proxy to `nginx:80` instead of `frontend:3000`):

```caddyfile
wardrobe.example.com {
	route {
		request_header -Remote-*
		request_header -X-Forward-Auth-Secret
		forward_auth tinyauth:3000 {
			uri /api/auth/caddy
			copy_headers Remote-User Remote-Email Remote-Name
		}
		reverse_proxy frontend:3000 {
			header_up X-Forward-Auth-Secret {$FORWARD_AUTH_SECRET}
		}
	}
}
```

`route` keeps the directives in the order written. Without it, Caddy runs `request_header` after `forward_auth` and would delete the headers TinyAuth just set.

**Traefik + Authelia**, as labels in a `docker-compose.override.yml` (put them on `nginx` with port `80` instead when using the prod compose, and attach Traefik to the stack's network):

```yaml
services:
  frontend:
    labels:
      traefik.enable: "true"
      traefik.http.routers.wardrobe.rule: Host(`wardrobe.example.com`)
      traefik.http.routers.wardrobe.entrypoints: websecure
      traefik.http.routers.wardrobe.middlewares: wardrobe-strip,authelia,wardrobe-secret
      traefik.http.services.wardrobe.loadbalancer.server.port: "3000"
      traefik.http.middlewares.wardrobe-strip.headers.customrequestheaders.Remote-User: ""
      traefik.http.middlewares.wardrobe-strip.headers.customrequestheaders.Remote-Email: ""
      traefik.http.middlewares.wardrobe-strip.headers.customrequestheaders.Remote-Name: ""
      traefik.http.middlewares.wardrobe-strip.headers.customrequestheaders.Remote-Groups: ""
      traefik.http.middlewares.wardrobe-strip.headers.customrequestheaders.X-Forward-Auth-Secret: ""
      traefik.http.middlewares.authelia.forwardauth.address: http://authelia:9091/api/authz/forward-auth
      traefik.http.middlewares.authelia.forwardauth.authResponseHeaders: Remote-User,Remote-Groups,Remote-Email,Remote-Name
      traefik.http.middlewares.wardrobe-secret.headers.customrequestheaders.X-Forward-Auth-Secret: ${FORWARD_AUTH_SECRET}
```

Traefik applies the middlewares in the listed order, and an empty `customrequestheaders` value removes that header.

> [!WARNING]
> The first time a `Remote-User` signs in, a `Remote-Email` that matches an existing account with a verified email joins that account, alongside its other sign-ins. OIDC sign-in does this only when the provider marks the email as verified, but the proxy sends no such flag, so Wardrowbe trusts every `Remote-Email`. The proxy's identity provider must therefore pass only emails it has verified. TinyAuth with a generic OAuth provider that lets people set an unverified email, or with an empty OAuth whitelist so that anyone can sign up there, lets someone claim an address they do not own and sign in to the matching Wardrowbe account. TinyAuth also makes up `<username>@<cookie domain>` for a local or LDAP user with no email, so give every such user their real address, or a username whose made-up address nobody else uses. This matters most when OIDC is configured alongside forward-auth, because the OIDC users' accounts are what such an email would join.
>
> If this database ever ran in development mode, anyone could also have signed in under any email address they typed. Check the existing users' emails before turning forward-auth on.

Accounts from before sign-in identities keep their old sign-in as a `legacy` identity, and a proxy username can be equal to one. A proxy sign-in claims it only when the account's email is verified and is either the proxy's `Remote-Email` or the placeholder older forward-auth versions stored when the proxy sent no email (`<Remote-User>@forward-auth.local` or `<Remote-User>@example.com`), and the account has no forward-auth identity yet. Those versions stored a non-ASCII username as its UTF-8 bytes read as Latin-1, and that spelling is matched too. The legacy identity stays, so the account's OIDC sign-in and its sessions from before the upgrade keep working. An account with an unverified email is skipped, and `Remote-Email` decides as for any new username. An account that already has a forward-auth identity and the proxy's exact email follows the email rule, so the two usernames take turns. Any other match is refused, and the login page reports a username conflict. To resolve it, either unlink the account's `legacy` identity by id with the transaction in [Accounts and sign-in identities](#accounts-and-sign-in-identities), so the proxy user gets an account of its own, or, if the proxy user owns the account, give the account the proxy user's address as a verified email, since an unverified one would make the next proxy sign-in move the address to a new account:

```sql
UPDATE users SET email = 'proxy-user@example.com', email_verified = true WHERE id = '<user id>';
```

The mobile app cannot sign in through a forward-auth proxy, so it needs OIDC. Both can be configured at once: set `OIDC_ISSUER_URL` and `OIDC_CLIENT_ID` alongside `FORWARD_AUTH_SECRET`, and browsers use the proxy while the app uses OIDC. The app has to reach Wardrowbe through a separate hostname that skips the forward-auth check, since it cannot complete the proxy's login page; expose only `/api/v1/` there. If it has to be a path on the browser's hostname instead, let it skip the check only for `/api/v1/`, never for pages or `/api/auth/`, since the app signs out a forward-auth session on any page load that did not come through the proxy. With that path, the browser's own API calls skip the proxy too, so a tab that is already open when the proxy user changes keeps acting as the previous user until it reloads.

> [!WARNING]
> Do not add `X-Forward-Auth-Secret` on the route the app uses. The app signs in with OIDC and never needs the secret, and a route that skips the proxy's check but still adds it lets anyone sign in as any user by sending their own `Remote-User` and `Remote-Email`. If your proxy can only add the secret on every route, that route must also strip every client-supplied `Remote-*` header first, as the snippets above do. An OIDC sign-in that then arrives with the secret but no `Remote-User` is still verified as OIDC.

### Notifications

- **ntfy.sh**: Free push notifications
- **Email**: SMTP-based (set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` in `.env`)

### Weather

Uses [Open-Meteo](https://open-meteo.com/) - free, no API key needed.

## Development

### Backend

```bash
# Run tests (requires running containers)
docker compose exec backend python -m pytest tests/ -v --tb=short

# Run a specific test file
docker compose exec backend python -m pytest tests/test_notification_workers.py -v

# Lint
pip install ruff
ruff check --fix backend/app/ && ruff format backend/app/
```

### Frontend

```bash
cd frontend
npm install

# Run dev server
npm run dev

# Run tests
npm test

# Build
npm run build
```

### API Documentation

Served only in dev mode (`DEBUG=true` with neither OIDC nor forward-auth configured):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Troubleshooting

### Build Fails with TypeScript Errors

```bash
# Check for type errors
cd frontend
npm install
npx tsc --noEmit

# If you see errors, please report them as a bug
```

### Frontend Shows "500 Internal Server Error" or Won't Load

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

### AI Features Not Working / Images Not Being Analyzed

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

### Development Mode Fails to Start

```bash
# 1. Ensure you're using the dev compose file
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
docker compose -f docker-compose.yml -f docker-compose.dev.yml build frontend
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 2. Check frontend logs
docker compose logs frontend -f

# Alternative: Run frontend locally for development
cd frontend
npm install
npm run dev
# Then access at http://localhost:3000
```

### Port Already in Use

```bash
# Check what's using the ports
sudo lsof -i :3000  # Frontend
sudo lsof -i :8000  # Backend
sudo lsof -i :5432  # PostgreSQL
sudo lsof -i :6379  # Redis

# Stop conflicting services or change ports in .env
```

### Database Migration Errors

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

### Container Keeps Restarting

```bash
# Check container logs
docker compose logs <service-name> --tail=100

# Common issues:
# - Database not ready: Wait 30 seconds and retry
# - Out of memory: Increase Docker memory limit
# - Permission errors: Check file permissions on volumes
```

### Performance Issues / Slow Response

```bash
# Check resource usage
docker stats

# If backend is slow:
# 1. Check PostgreSQL performance
docker compose exec postgres psql -U wardrobe -c "SELECT * FROM pg_stat_activity;"

# 2. Check Redis connection
docker compose exec redis redis-cli ping

# If AI analysis is slow:
# - For Ollama: Use smaller quantized models
# - For OpenAI: Check your rate limits
```

### Getting Help

If you're still stuck:
1. Check existing [GitHub Issues](https://github.com/yourusername/wardrowbe/issues)
2. Search [Discussions](https://github.com/yourusername/wardrowbe/discussions)
3. Create a new issue with:
   - Output of `docker compose ps`
   - Relevant logs from `docker compose logs`
   - Your .env configuration (redact secrets!)
   - Steps to reproduce the problem

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

If you find wardrowbe useful, consider supporting its development:

<a href="https://buymeacoffee.com/anyesh"><img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee"></a>

Thanks to our supporters:

- [@aaratisharma-star](https://github.com/aaratisharma-star)
- [@zkhcohen](https://github.com/zkhcohen)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Requirements

- Docker & Docker Compose
- ~4GB RAM (with local Ollama models)
- Storage for clothing photos

Works great on a Raspberry Pi 5!
