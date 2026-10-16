import type { NextAuthOptions, User } from 'next-auth';
import type { OAuthConfig } from 'next-auth/providers/oauth';
import CredentialsProvider from 'next-auth/providers/credentials';
import type { Provider } from 'next-auth/providers/index';
import { API_BASE_PATH } from '@/lib/api';
import {
  FORWARD_AUTH_ACCOUNT_CONFLICT,
  FORWARD_AUTH_SERVER_ERROR,
  FORWARD_AUTH_USERNAME_CONFLICT,
  LOCAL_INVALID_CREDENTIALS,
  LOCAL_SERVER_ERROR,
  LOCAL_TOO_MANY_ATTEMPTS,
  PASSKEY_REJECTED,
} from '@/lib/auth-errors';
import { decodeProxyHeader, proxySecretMatches } from '@/lib/proxy-headers';

interface OIDCProfile {
  sub: string;
  name?: string;
  preferred_username?: string;
  email?: string;
  picture?: string;
}

const OIDCProvider: OAuthConfig<OIDCProfile> = {
  id: 'oidc',
  name: 'SSO',
  type: 'oauth',
  wellKnown: `${process.env.OIDC_ISSUER_URL?.replace(/\/+$/, '')}/.well-known/openid-configuration`,
  clientId: process.env.OIDC_CLIENT_ID!,
  clientSecret: process.env.OIDC_CLIENT_SECRET!,
  authorization: {
    params: {
      scope: 'openid email profile',
    },
  },
  checks: ['pkce', 'state'],
  async profile(profile, tokens) {
    let email = profile.email;
    let name = profile.name || profile.preferred_username;

    if (!email && tokens.access_token && process.env.OIDC_ISSUER_URL) {
      try {
        const issuer = process.env.OIDC_ISSUER_URL.replace(/\/+$/, '');
        const discoveryRes = await fetch(`${issuer}/.well-known/openid-configuration`);
        if (discoveryRes.ok) {
          const discovery = await discoveryRes.json() as { userinfo_endpoint?: string };
          if (discovery.userinfo_endpoint) {
            const infoRes = await fetch(discovery.userinfo_endpoint, {
              headers: { Authorization: `Bearer ${tokens.access_token}` },
            });
            if (infoRes.ok) {
              const info = await infoRes.json() as { email?: string; name?: string; preferred_username?: string };
              email = info.email;
              name = name || info.name || info.preferred_username;
            }
          }
        }
      } catch {}
    }

    return {
      id: profile.sub,
      name,
      email,
      image: profile.picture,
    };
  },
};

// Dev credentials provider - for local development only
const DevCredentialsProvider = CredentialsProvider({
  id: 'dev-credentials',
  name: 'Dev Login',
  credentials: {
    email: { label: 'Email', type: 'email', placeholder: 'dev@example.com' },
    name: { label: 'Name', type: 'text', placeholder: 'Dev User' },
  },
  async authorize(credentials) {
    if (!credentials?.email) {
      return null;
    }

    // In dev mode, accept any email/name combination
    const email = credentials.email;
    const name = credentials.name || email.split('@')[0];
    const id = email.replace(/[^a-z0-9]/gi, '-').toLowerCase();

    return {
      id,
      email,
      name,
      image: null,
    };
  },
});

const FORWARDED_HEADERS = [
  'remote-user',
  'remote-email',
  'remote-name',
  'x-forward-auth-secret',
  'x-forwarded-for',
  'x-real-ip',
] as const;

type IncomingHeaders = Record<string, string | string[] | undefined>;

function backendUrl() {
  return process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';
}

function headerValue(headers: IncomingHeaders, name: string): string | undefined {
  const value = headers[name];
  return (Array.isArray(value) ? value[0] : value) || undefined;
}

// The backend answers 400 or 401 only when the proxy's headers or shared secret are wrong.
const PROXY_HEADER_REJECTIONS = new Set([400, 401]);
const LEGACY_IDENTITY_CONFLICT = 'legacy_identity_conflict';

// Undici waits 300 s for response headers, so a backend that accepts the connection and never
// answers would leave the login page on "Signing in" for five minutes without this bound.
export const SYNC_TIMEOUT_MS = 15_000;

// Matches the backend's SESSION_LIFETIME_HOURS default; a backend token that expires first signs
// the browser out on its next request anyway.
const DEFAULT_SESSION_HOURS = 168;
const sessionHours = Number(process.env.SESSION_LIFETIME_HOURS);
const SESSION_MAX_AGE_SECONDS =
  (Number.isFinite(sessionHours) && sessionHours > 0 ? sessionHours : DEFAULT_SESSION_HOURS) * 3600;

export async function authorizeForwardAuth(headers: IncomingHeaders): Promise<User | null> {
  const remoteUser = headerValue(headers, 'remote-user');
  const remoteEmail = headerValue(headers, 'remote-email');
  const presentedSecret = headerValue(headers, 'x-forward-auth-secret');
  // Without the secret the backend would fall through to its OIDC or dev branch, so this provider
  // must never call it without one.
  if (!remoteUser || !remoteEmail || !presentedSecret) {
    return null;
  }
  // The frontend checks the secret too, because the middleware ends a forward-auth session on every
  // request without it, which would loop through sign-in. The login page can only say the proxy's
  // headers are wrong, so a secret the frontend does not share is named here.
  if (!process.env.FORWARD_AUTH_SECRET) {
    console.error(
      'Forward-auth sign-in refused: FORWARD_AUTH_SECRET is not set for the frontend. Give it the backend\'s value.'
    );
    return null;
  }
  if (!proxySecretMatches(presentedSecret)) {
    console.error(
      "Forward-auth sign-in refused: X-Forward-Auth-Secret does not match the frontend's FORWARD_AUTH_SECRET."
    );
    return null;
  }

  const userId = decodeProxyHeader(remoteUser);

  // The raw header strings are relayed as-is, because fetch only accepts Latin-1 header values and
  // the backend applies the same UTF-8 decoding to the bytes.
  const forwarded: Record<string, string> = {};
  for (const name of FORWARDED_HEADERS) {
    const value = headerValue(headers, name);
    if (value) forwarded[name] = value;
  }

  // NextAuth turns a thrown message into the sign-in error code, so the login page can tell
  // a backend fault apart from headers the proxy did not pass.
  const serverError = (error: unknown) => {
    console.error('Forward-auth sync failed:', error);
    return new Error(FORWARD_AUTH_SERVER_ERROR);
  };

  const response = await fetch(`${backendUrl()}${API_BASE_PATH}/auth/sync`, {
    method: 'POST',
    headers: forwarded,
    signal: AbortSignal.timeout(SYNC_TIMEOUT_MS),
  }).catch((error: unknown) => {
    throw serverError(error);
  });

  if (PROXY_HEADER_REJECTIONS.has(response.status)) {
    const errorData = await response.json().catch(() => ({}));
    console.error('Forward-auth sync rejected:', errorData.detail || response.status);
    return null;
  }
  // A 409 means Remote-Email already belongs to a different account, or Remote-User names an
  // account from before sign-in identities whose email is not the proxy user's. Retrying cannot
  // fix either.
  if (response.status === 409) {
    const errorData = await response.json().catch(() => ({}));
    console.error('Forward-auth sync conflict:', errorData.detail || response.status);
    throw new Error(
      errorData.detail === LEGACY_IDENTITY_CONFLICT
        ? FORWARD_AUTH_USERNAME_CONFLICT
        : FORWARD_AUTH_ACCOUNT_CONFLICT
    );
  }
  if (!response.ok) {
    throw serverError(`Forward-auth sync answered ${response.status}`);
  }
  const syncData = await response.json().catch((error: unknown) => {
    throw serverError(error);
  });
  return {
    id: userId,
    email: syncData.email,
    name: syncData.display_name,
    accessToken: syncData.access_token,
    backendUserId: syncData.id,
    isNewUser: syncData.is_new_user,
    onboardingCompleted: syncData.onboarding_completed,
  };
}

// The backend rate-limits sign-in by client IP, and these requests reach it from the frontend
// container, so the client's forwarding headers are relayed (the backend trusts them only as far
// as TRUSTED_PROXY_COUNT allows).
const CLIENT_IP_HEADERS = ['x-forwarded-for', 'x-real-ip'] as const;

interface LocalSignInResponse {
  id: string;
  email: string;
  display_name: string;
  is_new_user: boolean;
  onboarding_completed: boolean;
  access_token: string;
}

async function localSignIn(
  path: string,
  body: unknown,
  headers: IncomingHeaders,
  rejected: string
): Promise<User> {
  const forwarded: Record<string, string> = { 'Content-Type': 'application/json' };
  for (const name of CLIENT_IP_HEADERS) {
    const value = headerValue(headers, name);
    if (value) forwarded[name] = value;
  }
  const response = await fetch(`${backendUrl()}${API_BASE_PATH}${path}`, {
    method: 'POST',
    headers: forwarded,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(SYNC_TIMEOUT_MS),
  }).catch((error: unknown) => {
    console.error(`Sign-in request to ${path} failed:`, error);
    throw new Error(LOCAL_SERVER_ERROR);
  });
  if (response.status === 429) throw new Error(LOCAL_TOO_MANY_ATTEMPTS);
  if (response.status === 400 || response.status === 401 || response.status === 422) {
    throw new Error(rejected);
  }
  if (!response.ok) {
    console.error(`Sign-in request to ${path} answered ${response.status}`);
    throw new Error(LOCAL_SERVER_ERROR);
  }
  const data = (await response.json().catch(() => null)) as LocalSignInResponse | null;
  if (!data?.access_token) throw new Error(LOCAL_SERVER_ERROR);
  return {
    id: data.id,
    email: data.email,
    name: data.display_name,
    accessToken: data.access_token,
    backendUserId: data.id,
    isNewUser: data.is_new_user,
    onboardingCompleted: data.onboarding_completed,
  };
}

export async function authorizePassword(
  credentials: Record<string, string> | undefined,
  headers: IncomingHeaders
): Promise<User | null> {
  const email = credentials?.email?.trim();
  const password = credentials?.password;
  if (!email || !password) return null;
  return localSignIn('/auth/login', { email, password }, headers, LOCAL_INVALID_CREDENTIALS);
}

export async function authorizePasskey(
  credentials: Record<string, string> | undefined,
  headers: IncomingHeaders
): Promise<User | null> {
  const flowId = credentials?.flowId;
  const raw = credentials?.credential;
  if (!flowId || !raw) return null;
  let credential: unknown;
  try {
    credential = JSON.parse(raw);
  } catch {
    throw new Error(PASSKEY_REJECTED);
  }
  return localSignIn(
    '/auth/passkeys/login/verify',
    { flow_id: flowId, credential },
    headers,
    PASSKEY_REJECTED
  );
}

const PasswordProvider = CredentialsProvider({
  id: 'password',
  name: 'Email and password',
  credentials: {
    email: { label: 'Email', type: 'email' },
    password: { label: 'Password', type: 'password' },
  },
  authorize: (credentials, req) => authorizePassword(credentials, req.headers ?? {}),
});

// The browser runs the WebAuthn ceremony against options from the backend; this provider hands
// the signed assertion to the backend, which verifies it and mints the session's token.
const PasskeyProvider = CredentialsProvider({
  id: 'passkey',
  name: 'Passkey',
  credentials: {
    flowId: { label: 'Flow', type: 'text' },
    credential: { label: 'Credential', type: 'text' },
  },
  authorize: (credentials, req) => authorizePasskey(credentials, req.headers ?? {}),
});

const ForwardAuthProvider = CredentialsProvider({
  id: 'forward-auth',
  name: 'Forward Auth',
  credentials: {},
  authorize: (_credentials, req) => authorizeForwardAuth(req.headers ?? {}),
});

function getProviders() {
  // The backend refuses password and passkey sign-in when LOCAL_AUTH_ENABLED=false, so these are
  // always registered and the login page asks the backend whether to offer them.
  const providers: Provider[] = [ForwardAuthProvider, PasswordProvider, PasskeyProvider];

  if (process.env.OIDC_ISSUER_URL) {
    providers.push(OIDCProvider);
  }

  if (process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development') {
    providers.push(DevCredentialsProvider);
  }
  return providers;
}

export const authOptions: NextAuthOptions = {
  providers: getProviders(),
  callbacks: {
    async jwt({ token, user, account, trigger, session }) {
      const apiUrl = backendUrl();

      // Session update triggered - refresh user data from backend
      if (trigger === 'update' && token.accessToken) {
        // A password change ends the session's backend token and hands the browser a new one.
        // A client can only put a token into its own session this way, and it is kept only once
        // the backend accepts it below.
        const replacement = (session as { accessToken?: unknown } | undefined)?.accessToken;
        const accessToken =
          typeof replacement === 'string' && replacement ? replacement : token.accessToken;
        try {
          const response = await fetch(`${apiUrl}${API_BASE_PATH}/users/me`, {
            headers: {
              'Authorization': `Bearer ${accessToken}`,
            },
          });

          if (response.ok) {
            const userData = await response.json();
            return {
              ...token,
              accessToken,
              onboardingCompleted: userData.onboarding_completed,
            };
          }
        } catch (error) {
          console.error('Failed to refresh user data:', error);
        }
        return token;
      }

      // Password and passkey sign-in got their backend token from authorize() directly.
      if (user && (account?.provider === 'password' || account?.provider === 'passkey')) {
        return {
          ...token,
          sub: user.id,
          accessToken: user.accessToken,
          backendUserId: user.backendUserId,
          isNewUser: user.isNewUser,
          onboardingCompleted: user.onboardingCompleted,
        };
      }

      // authorize() already synced with the proxy headers; a second sync from here would carry no
      // secret and be rejected.
      if (user && account?.provider === 'forward-auth') {
        return {
          ...token,
          sub: user.id,
          proxyUser: user.id,
          accessToken: user.accessToken,
          backendUserId: user.backendUserId,
          isNewUser: user.isNewUser,
          onboardingCompleted: user.onboardingCompleted,
        };
      }

      // Initial sign in - sync with backend and get API token
      if (user) {
        try {
          const response = await fetch(`${apiUrl}${API_BASE_PATH}/auth/sync`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              external_id: user.id,
              email: user.email,
              display_name: user.name || user.email?.split('@')[0] || 'User',
              avatar_url: user.image,
              id_token: account?.id_token,
            }),
            signal: AbortSignal.timeout(SYNC_TIMEOUT_MS),
          });

          if (response.ok) {
            const syncData = await response.json();
            return {
              ...token,
              accessToken: syncData.access_token,
              sub: user.id,
              backendUserId: syncData.id,
              isNewUser: syncData.is_new_user,
              onboardingCompleted: syncData.onboarding_completed,
            };
          }

          const errorData = await response.json().catch(() => ({}));
          const syncError = errorData.detail || `Backend sync failed (${response.status})`;
          console.error('Failed to sync user to backend:', syncError);
          return {
            ...token,
            sub: user.id,
            syncError,
          };
        } catch (error) {
          console.error('Failed to sync user to backend:', error);
        }

        return {
          ...token,
          sub: user.id,
          syncError: 'Unable to connect to backend server',
        };
      }
      return token;
    },
    async session({ session, token }) {
      return {
        ...session,
        user: {
          ...session.user,
          id: token.sub,
        },
        accessToken: token.accessToken,
        isNewUser: token.isNewUser,
        onboardingCompleted: token.onboardingCompleted,
        syncError: token.syncError,
      };
    },
  },
  pages: {
    signIn: '/login',
    error: '/login',
  },
  session: {
    strategy: 'jwt',
    maxAge: SESSION_MAX_AGE_SECONDS,
  },
  secret: process.env.NEXTAUTH_SECRET,
};
