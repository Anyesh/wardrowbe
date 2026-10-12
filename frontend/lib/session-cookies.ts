import type { NextRequest, NextResponse } from 'next/server';

const SESSION_COOKIE = 'next-auth.session-token';
const SECURE_PREFIX = '__Secure-';

// Mirrors getToken()'s default in next-auth/jwt so the middleware reads the cookie NextAuth wrote.
export function sessionCookie() {
  const secure = process.env.NEXTAUTH_URL?.startsWith('https://') ?? !!process.env.VERCEL;
  return { name: secure ? `${SECURE_PREFIX}${SESSION_COOKIE}` : SESSION_COOKIE, secure };
}

// Matches by prefix because NextAuth splits large sessions into `<name>.0`, `<name>.1`, ... and
// collects them with the same startsWith test. Both variants are cleared so a NEXTAUTH_URL that
// disagrees with the scheme the cookie was set under cannot leave a session behind.
export function clearSessionCookies(request: NextRequest, response: NextResponse) {
  for (const { name } of request.cookies.getAll()) {
    const secure = name.startsWith(`${SECURE_PREFIX}${SESSION_COOKIE}`);
    if (!secure && !name.startsWith(SESSION_COOKIE)) continue;
    // Browsers ignore a Set-Cookie for a __Secure- name unless it carries Secure.
    response.cookies.set(name, '', {
      path: '/',
      maxAge: 0,
      httpOnly: true,
      sameSite: 'lax',
      secure,
    });
  }
}
