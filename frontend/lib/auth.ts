import type { NextAuthOptions, User } from 'next-auth';
import type { OAuthConfig } from 'next-auth/providers/oauth';
import CredentialsProvider from 'next-auth/providers/credentials';
import type { Provider } from 'next-auth/providers/index';

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

// The backend alone verifies the secret; the frontend only relays what the proxy sent so that
// it holds no forward-auth configuration that could drift from the backend's.
export async function authorizeForwardAuth(headers: IncomingHeaders): Promise<User | null> {
  const remoteUser = headerValue(headers, 'remote-user');
  const remoteEmail = headerValue(headers, 'remote-email');
  // Without the secret the backend would fall through to its OIDC or dev branch, so this provider
  // must never call it without one.
  if (!remoteUser || !remoteEmail || !headerValue(headers, 'x-forward-auth-secret')) {
    return null;
  }

  const forwarded: Record<string, string> = { 'content-type': 'application/json' };
  for (const name of FORWARDED_HEADERS) {
    const value = headerValue(headers, name);
    if (value) forwarded[name] = value;
  }

  try {
    const response = await fetch(`${backendUrl()}/api/v1/auth/sync`, {
      method: 'POST',
      headers: forwarded,
      // The backend takes identity from the headers; the body only satisfies the request schema.
      body: JSON.stringify({
        external_id: remoteUser,
        email: remoteEmail,
        display_name: (headerValue(headers, 'remote-name') || remoteEmail.split('@')[0]).slice(0, 100),
      }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('Forward-auth sync rejected:', errorData.detail || response.status);
      return null;
    }
    const syncData = await response.json();
    return {
      id: remoteUser,
      email: syncData.email,
      name: syncData.display_name,
      accessToken: syncData.access_token,
      backendUserId: syncData.id,
      isNewUser: syncData.is_new_user,
      onboardingCompleted: syncData.onboarding_completed,
    };
  } catch (error) {
    console.error('Forward-auth sync failed:', error);
    return null;
  }
}

const ForwardAuthProvider = CredentialsProvider({
  id: 'forward-auth',
  name: 'Forward Auth',
  credentials: {},
  authorize: (_credentials, req) => authorizeForwardAuth(req.headers ?? {}),
});

function getProviders() {
  const providers: Provider[] = [ForwardAuthProvider];

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
    async jwt({ token, user, account, trigger }) {
      const apiUrl = backendUrl();

      // Session update triggered - refresh user data from backend
      if (trigger === 'update' && token.accessToken) {
        try {
          const response = await fetch(`${apiUrl}/api/v1/users/me`, {
            headers: {
              'Authorization': `Bearer ${token.accessToken}`,
            },
          });

          if (response.ok) {
            const userData = await response.json();
            return {
              ...token,
              onboardingCompleted: userData.onboarding_completed,
            };
          }
        } catch (error) {
          console.error('Failed to refresh user data:', error);
        }
        return token;
      }

      // authorize() already synced with the proxy headers; a second sync from here would carry no
      // secret and be rejected.
      if (user && account?.provider === 'forward-auth') {
        return {
          ...token,
          sub: user.id,
          accessToken: user.accessToken,
          backendUserId: user.backendUserId,
          isNewUser: user.isNewUser,
          onboardingCompleted: user.onboardingCompleted,
        };
      }

      // Initial sign in - sync with backend and get API token
      if (user) {
        try {
          const response = await fetch(`${apiUrl}/api/v1/auth/sync`, {
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
  },
  secret: process.env.NEXTAUTH_SECRET,
};
