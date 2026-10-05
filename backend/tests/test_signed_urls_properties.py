"""Properties of image links that grant access without a login session."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.utils import signed_urls


@settings(max_examples=75)
@given(
    user_id=st.uuids().map(str),
    stem=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
        min_size=1,
        max_size=40,
    ),
    lifetime=st.integers(min_value=1, max_value=86400),
)
def test_signed_image_link_only_authorizes_its_original_path(
    user_id: str, stem: str, lifetime: int
) -> None:
    now = 1_700_000_000
    path = f"{user_id}/{stem}.jpg"

    with patch.object(signed_urls.time, "time", return_value=now):
        url = urlsplit(signed_urls.sign_image_url(path, lifetime))
        query = parse_qs(url.query)
        expires = query["expires"][0]
        signature = query["sig"][0]

        assert url.path == f"/api/v1/images/{path}"
        assert int(expires) == now + lifetime
        assert signed_urls.verify_signature(path, expires, signature)
        assert not signed_urls.verify_signature(f"{user_id}/x{stem}.jpg", expires, signature)
        assert not signed_urls.verify_signature(path, str(int(expires) + 1), signature)

        changed_signature = ("0" if signature[0] != "0" else "1") + signature[1:]
        assert not signed_urls.verify_signature(path, expires, changed_signature)


@settings(max_examples=75)
@given(
    lifetime=st.integers(min_value=1, max_value=86400),
    elapsed=st.integers(min_value=1, max_value=86400),
)
def test_signed_image_link_expires_after_its_deadline(lifetime: int, elapsed: int) -> None:
    now = 1_700_000_000
    path = "00000000-0000-0000-0000-000000000001/photo.webp"
    with patch.object(signed_urls.time, "time", return_value=now):
        query = parse_qs(urlsplit(signed_urls.sign_image_url(path, lifetime)).query)
    expires = query["expires"][0]
    signature = query["sig"][0]

    with patch.object(signed_urls.time, "time", return_value=now + lifetime + elapsed):
        assert not signed_urls.verify_signature(path, expires, signature)


@pytest.mark.parametrize("expires", ["", "not-a-time", "1.5", "NaN"])
def test_signed_image_link_rejects_invalid_expiry(expires: str) -> None:
    with patch.object(signed_urls.hmac, "compare_digest", return_value=True) as compare:
        assert not signed_urls.verify_signature("image.jpg", expires, "0" * 32)
    compare.assert_not_called()
