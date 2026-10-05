import { NextResponse, type NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { clearSessionCookies, sessionCookie } from '@/lib/session-cookies';

// A proxy that switches users keeps the old NextAuth session cookie, and a GET to
// /api/auth/signout only renders a confirmation page, so the session is ended here.
export async function middleware(request: NextRequest) {
  const remoteUser = request.headers.get('remote-user');
  if (!remoteUser) return NextResponse.next();

  const { name, secure } = sessionCookie();
  const token = await getToken({ req: request, cookieName: name, secureCookie: secure });
  if (!token?.sub || token.sub === remoteUser) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  let response: NextResponse;
  if (pathname.startsWith('/api/v1/')) {
    response = NextResponse.json(
      { detail: 'The signed-in user changed at the proxy. Sign in again.' },
      { status: 401 }
    );
  } else {
    const login = request.nextUrl.clone();
    login.pathname = '/login';
    login.search = new URLSearchParams({ callbackUrl: `${pathname}${search}` }).toString();
    response = NextResponse.redirect(login);
  }
  clearSessionCookies(request, response);
  return response;
}

export const config = {
  matcher: ['/((?!api/auth|login|auth/logout|_next|favicon.ico).*)'],
};
