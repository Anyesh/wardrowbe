import logging
import ssl
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import get_settings

logger = logging.getLogger(__name__)

_jwk_clients: dict[tuple[str, str | None], PyJWKClient] = {}
_jwks_cache_times: dict[tuple[str, str | None], float] = {}
JWKS_CACHE_TTL = 3600


def _build_ssl_context(ca_bundle: str | None) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=ca_bundle)
    return ctx


def _get_jwk_client(jwks_uri: str, ca_bundle: str | None) -> PyJWKClient:
    cache_key = (jwks_uri, ca_bundle)
    now = time.time()
    cached_time = _jwks_cache_times.get(cache_key, 0)
    if cache_key in _jwk_clients and (now - cached_time) < JWKS_CACHE_TTL:
        return _jwk_clients[cache_key]

    client = PyJWKClient(jwks_uri, ssl_context=_build_ssl_context(ca_bundle))
    _jwk_clients[cache_key] = client
    _jwks_cache_times[cache_key] = now
    return client


async def validate_oidc_id_token(
    id_token: str,
    issuer_url: str,
    client_id: str | list[str],
) -> dict:
    settings = get_settings()
    ca_bundle = settings.oidc_ca_bundle

    try:
        discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        ssl_ctx = _build_ssl_context(ca_bundle) if ca_bundle else (not settings.debug)
        async with httpx.AsyncClient(timeout=10, verify=ssl_ctx, follow_redirects=True) as client:
            disc_resp = await client.get(discovery_url)
            disc_resp.raise_for_status()
            discovery = disc_resp.json()
            jwks_uri = discovery["jwks_uri"]
            # Validate the token's iss claim against the provider's canonical issuer
            # (the discovery metadata) rather than the configured env var, so a
            # trailing slash on OIDC_ISSUER_URL cannot cause a false issuer mismatch.
            expected_issuer = discovery.get("issuer", issuer_url.rstrip("/"))
    except httpx.HTTPError as e:
        logger.error("Failed to fetch OIDC discovery from %s: %s", issuer_url, e)
        raise ValueError("Failed to contact OIDC provider") from None

    audience = [client_id] if isinstance(client_id, str) else client_id

    try:
        jwk_client = _get_jwk_client(jwks_uri, ca_bundle=ca_bundle)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        payload: dict[str, Any] = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=expected_issuer,
            options={"verify_exp": True},
        )
    except jwt.PyJWTError:
        raise ValueError("Invalid OIDC token") from None

    return payload
