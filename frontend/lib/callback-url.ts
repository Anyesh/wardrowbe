const FALLBACK = '/dashboard';

function decodedPath(pathname: string): string | null {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return null;
  }
}

// The returned value is handed to router.push and signIn, so it must stay a path on this
// origin: a pathname that starts with // (or decodes to //, /\) reads as another host there.
export function safeCallbackUrl(value: string | null, origin: string): string {
  if (!value) return FALLBACK;
  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return FALLBACK;
  }
  if (url.origin !== origin) return FALLBACK;
  const decoded = decodedPath(url.pathname);
  if (decoded === null || /^[/\\]{2}/.test(decoded)) return FALLBACK;
  return `${url.pathname}${url.search}${url.hash}`;
}
