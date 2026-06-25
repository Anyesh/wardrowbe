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


class TestGetJwkClient:
    def test_cache_hit_returns_same_instance(self):
        oidc._jwk_clients.clear()
        oidc._jwks_cache_times.clear()

        uri = "https://auth.example.com/jwks/"
        with patch("app.utils.oidc.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = oidc._get_jwk_client(uri, ca_bundle=None)
            c2 = oidc._get_jwk_client(uri, ca_bundle=None)

        assert c1 is c2
        assert mock_cls.call_count == 1

    def test_different_ca_bundles_produce_separate_cache_entries(self):
        oidc._jwk_clients.clear()
        oidc._jwks_cache_times.clear()

        import ssl

        uri = "https://auth.example.com/jwks/"
        with (
            patch("app.utils.oidc.PyJWKClient") as mock_cls,
            patch("app.utils.oidc._build_ssl_context", return_value=MagicMock(spec=ssl.SSLContext)),
        ):
            mock_cls.side_effect = lambda *a, **kw: MagicMock()
            c_no_bundle = oidc._get_jwk_client(uri, ca_bundle=None)
            c_with_bundle = oidc._get_jwk_client(uri, ca_bundle="/certs/ca.pem")

        assert c_no_bundle is not c_with_bundle
        assert mock_cls.call_count == 2

    def test_ca_bundle_passed_to_pyjwkclient(self):
        oidc._jwk_clients.clear()
        oidc._jwks_cache_times.clear()

        import ssl

        uri = "https://auth.example.com/jwks/"
        with patch("app.utils.oidc.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            with patch("app.utils.oidc._build_ssl_context") as mock_ssl:
                mock_ssl.return_value = MagicMock(spec=ssl.SSLContext)
                oidc._get_jwk_client(uri, ca_bundle="/certs/ca.pem")
                mock_ssl.assert_called_once_with("/certs/ca.pem")
                _, kwargs = mock_cls.call_args
                assert kwargs["ssl_context"] is mock_ssl.return_value
