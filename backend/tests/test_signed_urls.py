from app.utils.signed_urls import sign_optional, verify_signature


def _parse(url: str) -> tuple[str, str, str]:
    path, query = url.removeprefix("/api/v1/images/").split("?")
    params = dict(part.split("=") for part in query.split("&"))
    return path, params["expires"], params["sig"]


class TestSignOptional:
    def test_none_returns_none(self):
        assert sign_optional(None) is None

    def test_empty_path_returns_none(self):
        assert sign_optional("") is None

    def test_path_is_signed(self):
        path, expires, sig = _parse(sign_optional("u/a_thumb.jpg"))
        assert path == "u/a_thumb.jpg"
        assert verify_signature(path, expires, sig)

    def test_fallback_used_only_when_path_missing(self):
        assert _parse(sign_optional(None, fallback="u/a.jpg"))[0] == "u/a.jpg"
        assert _parse(sign_optional("u/a_thumb.jpg", fallback="u/a.jpg"))[0] == "u/a_thumb.jpg"
