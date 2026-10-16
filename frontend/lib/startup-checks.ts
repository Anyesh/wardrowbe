const DEFAULT_NEXTAUTH_SECRET_PREFIX = 'change-me-in-production';

export function nextauthSecretProblem(env: Record<string, string | undefined>): string | null {
  const usesDefault = (env.NEXTAUTH_SECRET ?? '').startsWith(DEFAULT_NEXTAUTH_SECRET_PREFIX);
  // docker-compose passes LOCAL_AUTH_ENABLED to the frontend so this check covers built-in sign-in.
  const realAuth =
    !!env.OIDC_ISSUER_URL || !!env.FORWARD_AUTH_SECRET || env.LOCAL_AUTH_ENABLED === 'true';
  if (!usesDefault || !realAuth) return null;
  return (
    'NEXTAUTH_SECRET is still the default value. Set a secure NEXTAUTH_SECRET; the default ' +
    'is accepted only for local development with no real sign-in configured (built-in sign-in, ' +
    'OIDC or forward-auth).'
  );
}
