const utf8 = new TextDecoder('utf-8', { fatal: true });

// Node decodes header bytes as Latin-1, but proxies send UTF-8 names and ids verbatim. This mirrors
// the backend's _proxy_header so that the frontend keys a session by the same Remote-User the backend
// stores as external_id.
export function decodeProxyHeader(value: string): string {
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
