import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.utils import oidc

CANONICAL_ISSUER = "https://auth.example.com/application/o/wardrobe/"
CONFIGURED_ISSUER_NO_SLASH = "https://auth.example.com/application/o/wardrobe"
CLIENT_ID = "wardrobe"

FAKE_REQUEST = httpx.Request(
    "GET", f"{CONFIGURED_ISSUER_NO_SLASH}/.well-known/openid-configuration"
)


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_id_token(private_key, *, iss: str, aud: str = CLIENT_ID) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "user-1", "iss": iss, "aud": aud, "iat": now, "exp": now + 3600},
        private_key,
        algorithm="RS256",
    )


def _discovery_response(issuer: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"issuer": issuer, "jwks_uri": f"{issuer.rstrip('/')}/jwks/"},
        request=FAKE_REQUEST,
    )


def _patch_jwk_client(public_key):
    signing_key = MagicMock()
    signing_key.key = public_key
    jwk_client = MagicMock()
    jwk_client.get_signing_key_from_jwt.return_value = signing_key
    return patch.object(oidc, "_get_jwk_client", return_value=jwk_client)


class TestValidateOidcIdToken:
    @pytest.mark.asyncio
    async def test_accepts_token_when_issuer_claim_has_trailing_slash(self, rsa_key):
        # Authentik issues iss with a trailing slash; the configured env var omits
        # it. Validation must succeed because it checks the discovery issuer, not
        # the raw configured URL.
        token = _make_id_token(rsa_key, iss=CANONICAL_ISSUER)

        with (
            patch.object(
                httpx.AsyncClient,
                "get",
                new=AsyncMock(return_value=_discovery_response(CANONICAL_ISSUER)),
            ),
            _patch_jwk_client(rsa_key.public_key()),
        ):
            payload = await oidc.validate_oidc_id_token(
                token, CONFIGURED_ISSUER_NO_SLASH, CLIENT_ID
            )

        assert payload["sub"] == "user-1"
        assert payload["iss"] == CANONICAL_ISSUER

    @pytest.mark.asyncio
    async def test_rejects_token_from_wrong_issuer(self, rsa_key):
        token = _make_id_token(rsa_key, iss="https://evil.example.com/")

        with (
            patch.object(
                httpx.AsyncClient,
                "get",
                new=AsyncMock(return_value=_discovery_response(CANONICAL_ISSUER)),
            ),
            _patch_jwk_client(rsa_key.public_key()),
            pytest.raises(ValueError, match="Invalid OIDC token"),
        ):
            await oidc.validate_oidc_id_token(token, CONFIGURED_ISSUER_NO_SLASH, CLIENT_ID)

    @pytest.mark.asyncio
    async def test_raises_when_discovery_unreachable(self, rsa_key):
        token = _make_id_token(rsa_key, iss=CANONICAL_ISSUER)

        with (
            patch.object(
                httpx.AsyncClient,
                "get",
                new=AsyncMock(side_effect=httpx.ConnectError("refused")),
            ),
            pytest.raises(ValueError, match="Failed to contact OIDC provider"),
        ):
            await oidc.validate_oidc_id_token(token, CONFIGURED_ISSUER_NO_SLASH, CLIENT_ID)
