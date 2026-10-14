# Built-in sign-in: password and passkeys

Wardrowbe signs people in by itself, with an email and password or with a passkey
(Face ID, Touch ID, Windows Hello, Android, or a security key). Nothing outside your server is
involved: no cloud account, no external identity provider. OIDC and forward-auth
([forward-auth.md](forward-auth.md)) still work and can run next to it.

Every page and every API call needs a session. Pages without one redirect to `/login` on the
server, and the API answers `401` to any request without a valid token. Only `/login`, `/setup`,
`/health` and the sign-in endpoints are public.

## First start

1. Copy `.env.example` to `.env` and set at least:

   ```bash
   SECRET_KEY=<openssl rand -hex 32>
   NEXTAUTH_SECRET=<openssl rand -hex 32>
   POSTGRES_PASSWORD=<a strong password>
   APP_URL=https://wardrobe.example.com      # the address you open in the browser
   NEXTAUTH_URL=https://wardrobe.example.com
   ```

   The backend and the frontend refuse to start with the default `SECRET_KEY` /
   `NEXTAUTH_SECRET` while built-in sign-in is on, because anyone who knows the default could
   forge a session.

2. Start the stack:

   ```bash
   docker compose up -d            # pulls the published images
   docker compose up -d --build    # or builds them from this checkout
   ```

   The backend applies database migrations on start (`RUN_MIGRATIONS=true`).

3. Open the app. With no account yet, the login page sends you to **`/setup`**: enter your
   name, email and a password (at least 8 characters). That account is the **administrator**.
   As soon as it exists, `/setup` closes for good and redirects to the login page; the backend
   refuses any further setup request with `409`, even if two people submit at the same moment.

There is **no public registration**. The administrator adds the other accounts under
**Settings → Account & Security → Accounts**, or from the server:

```bash
docker compose exec backend python -m app.cli create-user someone@example.com --name "Someone"
docker compose exec backend python -m app.cli list-users
```

### Existing installs (data from dev login, OIDC or forward-auth)

The upgrade only adds columns and a table; accounts, clothes, outfits, photos and settings stay
as they are. Because accounts already exist, `/setup` stays closed. Give your existing account a
password from the server, which only someone with access to the host can do:

```bash
docker compose exec backend python -m app.cli set-password you@example.com --admin
```

The command asks for the password twice (`--password-stdin` reads it from standard input
instead). After that, sign in with that email and password.

## Password sign-in

- Passwords are hashed with **Argon2id** (`argon2-cffi`, RFC 9106 low-memory profile) and never
  stored or logged in clear. Older hashes are upgraded transparently on the next sign-in.
- A wrong password, an unknown email and a disabled account get the same answer, in the same
  time, so the login form does not reveal which accounts exist.
- Brute force is slowed twice: per client IP (20 attempts a minute), and per account (after 10
  failed attempts in 15 minutes the account refuses sign-ins until the window passes).
- A successful sign-in issues a new session; nothing from before sign-in is reused.

### Sessions

The browser holds the session in NextAuth's encrypted, `HttpOnly`, `SameSite=Lax` cookie, which
is `Secure` (and named `__Secure-…`) whenever `NEXTAUTH_URL` starts with `https://`. Nothing is
kept in `localStorage`. The cookie carries a backend token signed with `SECRET_KEY` that expires
after `SESSION_LIFETIME_HOURS` (default 168 = 7 days); an expired or revoked token signs the
browser out on its next request.

Changing the password ends **every other session** of the account, on every device. The
**Sign out** button (header, or Settings → Account & Security) ends the current session.

## Passkeys

1. Sign in with your password.
2. Go to **Settings → Account & Security → Passkeys**, type a name (for example *iPhone*,
   *MacBook* or *Windows Hello*; one is suggested) and press **Add passkey**.
3. Confirm with your current password, then follow the browser's prompt.

From then on, **Sign in with a passkey** on the login page signs you in without typing an email:
the browser offers the passkeys it has for this site. One account can hold several passkeys
(up to 20); each can be renamed or removed, and removing one asks for the password again.

What the server stores per passkey: credential ID, public key, signature counter, transports,
whether it is synced across devices, name, creation and last-use dates, and the owner. The
private key never leaves the authenticator.

Every ceremony uses a fresh random challenge generated on the server, kept in Redis for five
minutes and usable **once**. The backend checks the challenge, the origin, the RP ID, user
verification (biometrics or PIN) and the signature, and refuses a counter that does not move
forward (a sign of a cloned authenticator). Verification uses
[py_webauthn](https://github.com/duo-labs/py_webauthn); the browser side uses
[@simplewebauthn/browser](https://simplewebauthn.dev).

### HTTPS is required

Browsers only allow WebAuthn in a **secure context**: `https://`, or `http://localhost` on the
same machine. Opening Wardrowbe as `http://192.168.1.10:30300` from a phone or another PC works
for passwords, but the passkey button is disabled there with an explanation. To use passkeys from
other devices, put Wardrowbe behind HTTPS on a domain name.

Passkeys are bound to that domain. If you change it later, existing passkeys stop working (sign
in with your password and add them again).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_AUTH_ENABLED` | `true` | Built-in password + passkey sign-in. Also switches the open dev login off. Pass it to backend and frontend. |
| `SESSION_LIFETIME_HOURS` | `168` | Session length in hours. Pass it to backend and frontend. |
| `APP_URL` | `http://localhost:3000` | The public address; passkeys default to it. |
| `WEBAUTHN_RP_ID` | host of `APP_URL` | Domain passkeys are bound to: no scheme, no port (`wardrobe.example.com`). It may be a parent domain of the origin (`example.com`). |
| `WEBAUTHN_RP_NAME` | `Wardrowbe` | Name the browser shows in the passkey prompt. |
| `WEBAUTHN_ORIGIN` | origin of `APP_URL` | Exact origin(s) the browser shows, comma-separated: `https://wardrobe.example.com` or `https://wardrobe.example.com:8443`. |
| `RUN_MIGRATIONS` | `true` (backend service) | Apply database migrations when the backend starts. |
| `WARDROWBE_IMAGE` / `WARDROWBE_TAG` | `ghcr.io/theblackside243/wardrowbe` / `latest` | Images the compose files pull. |

At start-up the backend logs a `Passkeys:` warning when these settings cannot work, for example
an `http://` address that is not localhost, or an RP ID that does not match the origin.

## Behind a reverse proxy

Wardrowbe needs no code change behind Traefik, Nginx Proxy Manager, Caddy or the TrueNAS app
proxy. Point the proxy at the **frontend** (port 3000 inside the stack): it serves the pages and
forwards `/api/v1` to the backend itself. Then:

- `APP_URL` and `NEXTAUTH_URL` = the https address people type, e.g.
  `https://wardrobe.example.com`. Leave `WEBAUTHN_*` empty unless the address differs.
- The proxy must pass the original `Host` and terminate TLS; websockets are not needed.
- Optional: set `TRUSTED_PROXY_COUNT=1` on the backend so that sign-in rate limits see the real
  client IP from `X-Forwarded-For` (see *Client IPs behind a reverse proxy* in the README). Only
  do this when the proxy is the only way in, otherwise a client could pick its own IP.

Examples:

```caddyfile
wardrobe.example.com {
    reverse_proxy 192.168.1.10:3000
}
```

```yaml
# Traefik labels on the frontend service
labels:
  - traefik.enable=true
  - traefik.http.routers.wardrobe.rule=Host(`wardrobe.example.com`)
  - traefik.http.routers.wardrobe.entrypoints=websecure
  - traefik.http.routers.wardrobe.tls.certresolver=letsencrypt
  - traefik.http.services.wardrobe.loadbalancer.server.port=3000
```

In **Nginx Proxy Manager**, add a Proxy Host for `wardrobe.example.com` to
`http://<server-ip>:<frontend port>`, request a Let's Encrypt certificate and enable *Force SSL*.

## TrueNAS SCALE

1. Create datasets for the persistent data, for example `apps/wardrowbe/postgres`,
   `apps/wardrowbe/redis` and `apps/wardrowbe/data`.
2. **Apps → Discover Apps → ⋮ → Install via YAML** (Custom App). Paste
   [`docker-compose.yml`](../docker-compose.yml) and change, for each service:
   - the named volumes to host paths on your datasets, e.g.
     `- /mnt/<pool>/apps/wardrowbe/data:/data/wardrobe` for backend, worker and image-worker,
     `- /mnt/<pool>/apps/wardrowbe/postgres:/var/lib/postgresql/data` for postgres;
   - the `${…}` values you need (TrueNAS has no `.env` file, so write them in the YAML or in
     the app's environment): `SECRET_KEY`, `NEXTAUTH_SECRET`, `POSTGRES_PASSWORD`, `APP_URL`,
     `NEXTAUTH_URL`, the `AI_*` settings;
   - the published ports if 3000/8000/5432/6379 are taken. Postgres and Redis do not need to be
     published at all.
3. Make the data datasets writable by the containers: the backend runs as `PUID`/`PGID`
   (default 1000), Postgres as its own user. The simplest is to set the dataset owner to the
   `PUID` you choose.
4. Install, open `http://<truenas-ip>:3000`, and create the administrator on `/setup`.
5. For passkeys from your phone, add the HTTPS proxy (Nginx Proxy Manager or the TrueNAS
   proxy) as above and set `APP_URL` / `NEXTAUTH_URL` to the https address.

## Backup

Back up these and nothing else is lost:

| What | Where | Contains |
| --- | --- | --- |
| PostgreSQL data | volume `postgres_data` (or its dataset) | accounts, password hashes, passkeys, clothes, outfits, settings |
| Photos | volume `wardrobe_data` → `/data/wardrobe` | uploaded and processed images |
| `.env` (or the app's YAML) | your checkout / TrueNAS app config | `SECRET_KEY`, `NEXTAUTH_SECRET`, database password |

For a consistent database copy, prefer a dump over copying the files of a running database:

```bash
docker compose exec postgres pg_dump -U wardrobe wardrobe > wardrowbe.sql
```

Redis only holds job queues, rate limits and short-lived passkey challenges; it does not need a
backup. If `SECRET_KEY` changes, everyone has to sign in again; passwords and passkeys keep
working.

## Turning it off

`LOCAL_AUTH_ENABLED=false` (on backend and frontend) restores the previous behaviour: OIDC or
forward-auth if configured, otherwise dev login with `DEBUG=true`. Passwords and passkeys stay in
the database for when it is turned on again.
