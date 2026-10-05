import { NextResponse, type NextRequest } from 'next/server';
import { clearSessionCookies } from '@/lib/session-cookies';

// loggedOut=1 stops the login page from signing straight back in through a proxy session
// that outlived the logout.
function logoutTarget(loggedOutUrl: string) {
  const forwardAuthLogoutUrl = process.env.FORWARD_AUTH_LOGOUT_URL;
  const tinyAuthUrl = process.env.TINYAUTH_URL?.replace(/\/+$/, '');
  const endSessionUrl = process.env.OIDC_END_SESSION_URL;

  if (forwardAuthLogoutUrl) return forwardAuthLogoutUrl;
  if (tinyAuthUrl) return `${tinyAuthUrl}/logout?redirect_uri=${encodeURIComponent(loggedOutUrl)}`;
  if (endSessionUrl) {
    return `${endSessionUrl}?post_logout_redirect_uri=${encodeURIComponent(loggedOutUrl)}`;
  }
  return loggedOutUrl;
}

export async function GET(request: NextRequest) {
  const appUrl = process.env.NEXTAUTH_URL?.replace(/\/+$/, '') || request.nextUrl.origin;
  const response = NextResponse.redirect(logoutTarget(`${appUrl}/login?loggedOut=1`), 302);
  clearSessionCookies(request, response);
  return response;
}
