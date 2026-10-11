import { NextResponse, type NextRequest } from 'next/server';
import { getToken, type JWT } from 'next-auth/jwt';
import { decodeProxyHeader, proxySecretMatches } from '@/lib/proxy-headers';
import { clearSessionCookies, sessionCookie } from '@/lib/session-cookies';

// A proxy that switches users keeps the old NextAuth session cookie, and a GET to
// /api/auth/signout only renders a confirmation page, so the session is ended here.
const NEXTAUTH_PREFIX = '/api/auth/';
const LOGIN_PATH = '/login';

// NextAuth answers the session action for any path whose first segment after /api/auth decodes
// to "session", such as /api/auth/session/x or /api/auth/%73ession.
function nextAuthAction(pathname: string): string | null {
  if (!pathname.startsWith(NEXTAUTH_PREFIX)) return null;
  const segment = pathname.slice(NEXTAUTH_PREFIX.length).split('/')[0];
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

// A forward-auth session is kept only on a request that came through the proxy for its own user,
// so a request past the proxy cannot read it back with a forged Remote-User. Behind the proxy the
// login page offers forward-auth alone, so an OIDC or dev session there was left by whoever used
// the browser before, and its token still works wherever the backend is reached without the
// secret. Without this deployment's secret the request may come from a proxy in front of an OIDC
// deployment, which must keep its sessions.
function belongsToRequest(token: JWT, request: NextRequest): boolean {
  const proxied = proxySecretMatches(request.headers.get('x-forward-auth-secret'));
  if (!token.proxyUser) return !proxied;
  const rawRemoteUser = request.headers.get('remote-user');
  return proxied && rawRemoteUser !== null && token.proxyUser === decodeProxyHeader(rawRemoteUser);
}

async function sessionToken(request: NextRequest): Promise<JWT | null> {
  const { name, secure } = sessionCookie();
  try {
    return await getToken({ req: request, cookieName: name, secureCookie: secure });
  } catch (error) {
    // getToken decodes an Authorization bearer value outside its own error handling, and a
    // malformed one carries no session.
    if (error instanceof URIError) return null;
    throw error;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === LOGIN_PATH) {
    const response = NextResponse.next();
    if (request.nextUrl.searchParams.get('loggedOut') === '1') clearSessionCookies(request, response);
    return response;
  }
  const action = nextAuthAction(pathname);
  // Every other NextAuth action, sign-in included, has to work for the new proxy user.
  if (action !== null && action !== 'session') return NextResponse.next();

  const token = await sessionToken(request);
  if (!token || belongsToRequest(token, request)) return NextResponse.next();
  if (!token.proxyUser) {
    // The login page offers OIDC or dev sign-in when the backend has no forward-auth secret, so a
    // frontend that has one would end each of those sessions with nothing on screen to say why.
    console.warn(
      'Ended an OIDC or dev session on a request through the forward-auth proxy. If this repeats after ' +
        'every sign-in, the frontend has FORWARD_AUTH_SECRET but the backend does not.'
    );
  }

  let response: NextResponse;
  if (action === 'session') {
    // Answered as signed out rather than redirected, because the client reads it as JSON and
    // must never receive the previous user's backend token.
    response = NextResponse.json({});
  } else {
    const login = request.nextUrl.clone();
    login.pathname = '/login';
    login.search = new URLSearchParams({ callbackUrl: `${pathname}${search}` }).toString();
    response = NextResponse.redirect(login);
  }
  clearSessionCookies(request, response);
  return response;
}

// API routes are left out, because Next buffers the whole body of every matched non-GET request
// before forwarding it, uploads included, and the backend refuses a switched proxy user itself.
// NextAuth's routes are the exception, since its session action hands the backend token to the
// browser. Static files (any path with an extension) carry no session and are left out too.
//
// The logout route clears the session before sending the browser to /login?loggedOut=1, but a
// session request still in flight in another tab sets the cookie again when it answers, so the
// logged-out page clears it once more.
export const config = {
  matcher: [
    '/((?!api/|login|auth/logout|_next|.*\\..*).*)',
    '/api/auth/:path*',
    { source: '/login', has: [{ type: 'query', key: 'loggedOut', value: '1' }] },
  ],
};
