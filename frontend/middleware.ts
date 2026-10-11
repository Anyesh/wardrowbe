import { NextResponse, type NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { decodeProxyHeader } from '@/lib/proxy-headers';
import { clearSessionCookies, sessionCookie } from '@/lib/session-cookies';

// A proxy that switches users keeps the old NextAuth session cookie, and a GET to
// /api/auth/signout only renders a confirmation page, so the session is ended here. Only a
// forward-auth session is compared, because an OIDC or dev session behind a proxy that also
// sends Remote-User was never that user's, and the backend refuses its API calls itself.
export async function middleware(request: NextRequest) {
  const rawRemoteUser = request.headers.get('remote-user');
  if (!rawRemoteUser) return NextResponse.next();
  const remoteUser = decodeProxyHeader(rawRemoteUser);

  const { name, secure } = sessionCookie();
  const token = await getToken({ req: request, cookieName: name, secureCookie: secure });
  if (!token?.proxyUser || token.proxyUser === remoteUser) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  const login = request.nextUrl.clone();
  login.pathname = '/login';
  login.search = new URLSearchParams({ callbackUrl: `${pathname}${search}` }).toString();
  const response = NextResponse.redirect(login);
  clearSessionCookies(request, response);
  return response;
}

// API routes are left out, because Next buffers the whole body of every matched non-GET request
// before forwarding it, uploads included, and the backend refuses a switched proxy user itself.
export const config = {
  matcher: ['/((?!api/|login|auth/logout|_next|favicon.ico).*)'],
};
