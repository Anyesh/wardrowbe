# Forward-auth (TinyAuth, Authelia)

Forward-auth lets an authenticating reverse proxy sign people in to Wardrowbe. It works like this:

1. The proxy (TinyAuth or Authelia behind Caddy, Traefik or nginx) authenticates the browser and adds `Remote-User`, `Remote-Email`, optionally `Remote-Name`, and a static `X-Forward-Auth-Secret` header to every request it forwards.
2. On `/login` the app signs in by itself: the backend checks the secret, then signs in the forward-auth identity named by `Remote-User`, creating an account for it when no account matches (see [Accounts and sign-in identities](sign-in-identities.md#accounts-and-sign-in-identities)). A wrong secret is refused, and `Remote-*` headers sent without the secret are ignored.
3. After sign-in, requests use Wardrowbe's own session token, and the proxy headers never sign a request in.
4. Logging out ends the Wardrowbe session, then sends the browser to the proxy's logout page so the proxy session ends too (TinyAuth's page asks for one more click).

<details>
<summary>What happens to a session when the proxy user changes</summary>

The proxy headers can only refuse a request: a request that carries the right secret and a `Remote-User` that is not a forward-auth identity of the session's account gets a 401. Image links the app already handed out are signed and keep working until they expire. So if the proxy starts reporting a different `Remote-User`, the next page load signs the old session out, and a tab that is already open has its API calls refused until it reloads (unless those calls skip the proxy, see the mobile app below). A page load also signs out a forward-auth session that reaches the app without the secret or without `Remote-User`, and an OIDC or development session in a browser the proxy now serves, since the login page offers only forward-auth there.

</details>

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

<details>
<summary>Sign-in fails when only one service has the secret</summary>

If only one of the two services gets the secret, sign-in fails. With only the backend's, the login page reports missing proxy headers and the frontend log says its `FORWARD_AUTH_SECRET` is not set. With only the frontend's, the login page offers OIDC or development sign-in, and every page load through the proxy signs that session out again, with a warning in the frontend log.

</details>

Put the proxy in front of the frontend on `:3000` with the default `docker-compose.yml`, or in front of nginx on `:8080` with `docker-compose.prod.yml`. Only the proxy should be able to reach those ports. The prod compose already binds nginx to `127.0.0.1` and publishes nothing else; with the default compose, set `FRONTEND_PORT=127.0.0.1:3000` and `BACKEND_PORT=127.0.0.1:8000` in `.env` (or remove the `ports:` entries if the proxy shares the stack's Docker network), so nobody on your LAN can skip the proxy or watch the secret go past in plain HTTP.

Then set `TRUSTED_PROXY_COUNT` to `1` with the default compose or `2` with the prod compose, so sign-in rate limits see each browser's address instead of the proxy's (see [Client IPs behind a reverse proxy](../README.md#client-ips-behind-a-reverse-proxy)).

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

<details>
<summary>Accounts from before sign-in identities</summary>

Accounts from before sign-in identities keep their old sign-in as a `legacy` identity, and a proxy username can be equal to one. A proxy sign-in claims it only when the account's email is verified and is either the proxy's `Remote-Email` or the placeholder older forward-auth versions stored when the proxy sent no email (`<Remote-User>@forward-auth.local` or `<Remote-User>@example.com`), and the account has no forward-auth identity yet. Those versions stored a non-ASCII username as its UTF-8 bytes read as Latin-1, and that spelling is matched too. The legacy identity stays, so the account's OIDC sign-in and its sessions from before the upgrade keep working. An account with an unverified email is skipped, and `Remote-Email` decides as for any new username. An account that already has a forward-auth identity and the proxy's exact email follows the email rule, so the two usernames take turns. Any other match is refused, and the login page reports a username conflict. To resolve it, either unlink the account's `legacy` identity by id with the transaction in [Accounts and sign-in identities](sign-in-identities.md#accounts-and-sign-in-identities), so the proxy user gets an account of its own, or, if the proxy user owns the account, give the account the proxy user's address as a verified email, since an unverified one would make the next proxy sign-in move the address to a new account:

```sql
UPDATE users SET email = 'proxy-user@example.com', email_verified = true WHERE id = '<user id>';
```

</details>

<details>
<summary>Using the mobile app alongside forward-auth</summary>

The mobile app cannot sign in through a forward-auth proxy, so it needs OIDC. Both can be configured at once: set `OIDC_ISSUER_URL` and `OIDC_CLIENT_ID` alongside `FORWARD_AUTH_SECRET`, and browsers use the proxy while the app uses OIDC. The app has to reach Wardrowbe through a separate hostname that skips the forward-auth check, since it cannot complete the proxy's login page; expose only `/api/v1/` there. If it has to be a path on the browser's hostname instead, let it skip the check only for `/api/v1/`, never for pages or `/api/auth/`, since the app signs out a forward-auth session on any page load that did not come through the proxy. With that path, the browser's own API calls skip the proxy too, so a tab that is already open when the proxy user changes keeps acting as the previous user until it reloads.

</details>

> [!WARNING]
> Do not add `X-Forward-Auth-Secret` on the route the app uses. The app signs in with OIDC and never needs the secret, and a route that skips the proxy's check but still adds it lets anyone sign in as any user by sending their own `Remote-User` and `Remote-Email`. If your proxy can only add the secret on every route, that route must also strip every client-supplied `Remote-*` header first, as the snippets above do. An OIDC sign-in that then arrives with the secret but no `Remote-User` is still verified as OIDC.
