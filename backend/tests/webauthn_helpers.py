"""A software WebAuthn authenticator for tests.

It produces the same RegistrationResponseJSON and AuthenticationResponseJSON a browser hands to
the page, with a real P-256 key and "none" attestation, so py_webauthn verifies them exactly as it
would a phone's or a security key's.
"""

import hashlib
import json
import os
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


class SoftAuthenticator:
    def __init__(self, rp_id: str = "localhost", origin: str = "http://localhost:3000"):
        self.rp_id = rp_id
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0
        self.user_handle: bytes | None = None

    def _cose_public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, ceremony: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {
                "type": ceremony,
                "challenge": challenge,
                "origin": origin or self.origin,
                "crossOrigin": False,
            }
        ).encode()

    def _authenticator_data(self, flags: int, rp_id: str | None, attested: bool) -> bytes:
        data = (
            hashlib.sha256((rp_id or self.rp_id).encode()).digest()
            + bytes([flags])
            + self.sign_count.to_bytes(4, "big")
        )
        if attested:
            data += (
                bytes(16)  # AAGUID: none
                + len(self.credential_id).to_bytes(2, "big")
                + self.credential_id
                + self._cose_public_key()
            )
        return data

    def register(
        self,
        options: dict[str, Any],
        *,
        origin: str | None = None,
        rp_id: str | None = None,
        challenge: str | None = None,
    ) -> dict[str, Any]:
        self.user_handle = base64url_to_bytes(options["user"]["id"])
        client_data = self._client_data(
            "webauthn.create", challenge or options["challenge"], origin
        )
        auth_data = self._authenticator_data(FLAG_UP | FLAG_UV | FLAG_AT, rp_id, attested=True)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        encoded_id = bytes_to_base64url(self.credential_id)
        return {
            "id": encoded_id,
            "rawId": encoded_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal", "hybrid", "not-a-transport"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def assertion(
        self,
        options: dict[str, Any],
        *,
        origin: str | None = None,
        challenge: str | None = None,
        user_verified: bool = True,
        advance_counter: bool = True,
        signing_key: ec.EllipticCurvePrivateKey | None = None,
    ) -> dict[str, Any]:
        if advance_counter:
            self.sign_count += 1
        client_data = self._client_data("webauthn.get", challenge or options["challenge"], origin)
        flags = FLAG_UP | (FLAG_UV if user_verified else 0)
        auth_data = self._authenticator_data(flags, None, attested=False)
        signature = (signing_key or self.key).sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        encoded_id = bytes_to_base64url(self.credential_id)
        return {
            "id": encoded_id,
            "rawId": encoded_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(self.user_handle or b""),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
