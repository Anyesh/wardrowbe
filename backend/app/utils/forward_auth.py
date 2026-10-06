import hmac

from starlette.datastructures import Headers

FORWARD_AUTH_SECRET_HEADER = "X-Forward-Auth-Secret"

# Only HTTP's own optional whitespace is trimmed, and only after decoding, because str.strip()
# also removes \x85 and \xa0, which are the final bytes of UTF-8 characters such as Å and à.
PROXY_HEADER_WHITESPACE = " \t"


def proxy_header(headers: Headers, name: str) -> str:
    value = headers.get(name, "")
    # Starlette decodes header bytes as latin-1, but proxies send UTF-8 names and ids
    # verbatim, so a non-ASCII Remote-Name would otherwise arrive as mojibake.
    try:
        decoded = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        decoded = value
    return decoded.strip(PROXY_HEADER_WHITESPACE)


def forward_auth_secret_matches(presented: str | None, expected: str | None) -> bool:
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())
