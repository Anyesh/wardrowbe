const utf8 = new TextDecoder('utf-8', { fatal: true });

// Only HTTP's own optional whitespace, trimmed after decoding, matches the backend: a broader trim
// would drop U+00A0, and trimming before decoding would cut the last byte of à or Å.
const OPTIONAL_WHITESPACE = /^[ \t]+|[ \t]+$/g;

function decodeUtf8(value: string): string {
  const bytes = new Uint8Array(value.length);
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code > 0xff) return value;
    bytes[i] = code;
  }
  try {
    return utf8.decode(bytes);
  } catch {
    return value;
  }
}

// Node decodes header bytes as Latin-1, but proxies send UTF-8 names and ids verbatim. This mirrors
// the backend's proxy_header so that the frontend keys a session by the same Remote-User the backend
// stores as the forward-auth identity's subject.
export function decodeProxyHeader(value: string): string {
  return decodeUtf8(value).replace(OPTIONAL_WHITESPACE, '');
}

// The same check the backend makes, so that the frontend treats a request as coming through the
// forward-auth proxy only when the backend would. It runs in constant time like the backend's
// hmac.compare_digest, because the Edge runtime has no crypto.timingSafeEqual.
export function proxySecretMatches(presented: string | null | undefined): boolean {
  const expected = process.env.FORWARD_AUTH_SECRET;
  if (!presented || !expected) return false;
  let difference = presented.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) {
    difference |= expected.charCodeAt(i) ^ presented.charCodeAt(i);
  }
  return difference === 0;
}
