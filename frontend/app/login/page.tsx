'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { signIn, getProviders, getSession, useSession } from 'next-auth/react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Fingerprint, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { API_BASE_PATH } from '@/lib/api';
import { safeCallbackUrl } from '@/lib/callback-url';
import {
  FORWARD_AUTH_ACCOUNT_CONFLICT,
  FORWARD_AUTH_SERVER_ERROR,
  FORWARD_AUTH_USERNAME_CONFLICT,
  LOCAL_INVALID_CREDENTIALS,
  LOCAL_TOO_MANY_ATTEMPTS,
  PASSKEY_REJECTED,
} from '@/lib/auth-errors';
import { useAuthConfig } from '@/lib/hooks/use-auth-config';
import { PasskeyCeremonyError, getPasskeyAssertion, passkeySupport } from '@/lib/passkeys';

function OIDCLoginButton({ getCallbackUrl }: { getCallbackUrl: () => string }) {
  const t = useTranslations('auth');

  return (
    <button
      onClick={() => signIn('oidc', { callbackUrl: getCallbackUrl() })}
      className="flex w-full items-center justify-center gap-3 rounded-md bg-primary px-4 py-3 text-primary-foreground hover:bg-primary/90 transition-colors"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
      </svg>
      {t('title')}
    </button>
  );
}

function DevLogin({ getCallbackUrl }: { getCallbackUrl: () => string }) {
  const [email, setEmail] = useState('dev@wardrobe.local');
  const [name, setName] = useState('Dev User');
  const [isLoading, setIsLoading] = useState(false);
  const t = useTranslations('auth');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    await signIn('dev-credentials', {
      email,
      name,
      callbackUrl: getCallbackUrl(),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-md bg-yellow-500/10 border border-yellow-500/20 p-3 text-sm text-yellow-600 dark:text-yellow-400">
        {t('devMode')}
      </div>
      <div className="space-y-2">
        <label htmlFor="email" className="block text-sm font-medium">
          {t('email')}
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="dev@example.com"
        />
      </div>
      <div className="space-y-2">
        <label htmlFor="name" className="block text-sm font-medium">
          {t('displayName')}
        </label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder={t('namePlaceholder')}
        />
      </div>
      <button
        type="submit"
        disabled={isLoading}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('signingIn')}
          </>
        ) : (
          t('title')
        )}
      </button>
    </form>
  );
}

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+$/;

type LocalErrorKey =
  | 'local.invalidCredentials'
  | 'local.tooManyAttempts'
  | 'local.serverError'
  | 'local.emailRequired'
  | 'local.emailInvalid'
  | 'local.passwordRequired'
  | 'passkey.cancelled'
  | 'passkey.unsupported'
  | 'passkey.insecure'
  | 'passkey.rejected'
  | 'passkey.failed';

function localErrorFor(code: string | null | undefined): LocalErrorKey {
  if (code === LOCAL_INVALID_CREDENTIALS || code === 'CredentialsSignin') return 'local.invalidCredentials';
  if (code === LOCAL_TOO_MANY_ATTEMPTS) return 'local.tooManyAttempts';
  if (code === PASSKEY_REJECTED) return 'passkey.rejected';
  return 'local.serverError';
}

function passkeyErrorFor(error: unknown): LocalErrorKey {
  if (!(error instanceof PasskeyCeremonyError)) return 'passkey.failed';
  if (error.reason === 'cancelled') return 'passkey.cancelled';
  if (error.reason === 'unsupported') return 'passkey.unsupported';
  if (error.reason === 'insecure') return 'passkey.insecure';
  return 'passkey.failed';
}

function LocalLogin({ showOidc, getCallbackUrl }: { showOidc: boolean; getCallbackUrl: () => string }) {
  const t = useTranslations('auth');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState<'password' | 'passkey' | null>(null);
  const [error, setError] = useState<LocalErrorKey | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: LocalErrorKey; password?: LocalErrorKey }>({});
  const [support, setSupport] = useState<ReturnType<typeof passkeySupport> | null>(null);

  // Read after mount: the server render has no window to ask.
  useEffect(() => setSupport(passkeySupport()), []);

  const finish = useCallback(async (result: Awaited<ReturnType<typeof signIn>>) => {
    if (!result?.ok || result.error) {
      setError(localErrorFor(result?.error));
      setPending(null);
      return;
    }
    // The page's redirect effect takes over once the new session arrives; if another tab ended it
    // first, the form must not stay disabled.
    const session = await getSession();
    if (!session?.accessToken) setPending(null);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    const errors: typeof fieldErrors = {};
    if (!trimmed) errors.email = 'local.emailRequired';
    else if (!EMAIL_PATTERN.test(trimmed)) errors.email = 'local.emailInvalid';
    if (!password) errors.password = 'local.passwordRequired';
    setFieldErrors(errors);
    setError(null);
    if (errors.email || errors.password) return;
    setPending('password');
    const result = await signIn('password', { email: trimmed, password, redirect: false });
    if (!result?.ok || result.error) setPassword('');
    await finish(result);
  };

  const handlePasskey = async () => {
    setError(null);
    setFieldErrors({});
    setPending('passkey');
    let assertion;
    try {
      assertion = await getPasskeyAssertion();
    } catch (err) {
      setError(passkeyErrorFor(err));
      setPending(null);
      return;
    }
    const result = await signIn('passkey', { ...assertion, redirect: false });
    await finish(result);
  };

  const busy = pending !== null;

  return (
    <div className="space-y-6">
      {error && (
        <div role="alert" className="rounded-md bg-destructive/15 p-4 text-sm text-destructive">
          {t(error)}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-4" aria-busy={pending === 'password'}>
        <div className="space-y-2">
          <Label htmlFor="login-email">{t('email')}</Label>
          <Input
            id="login-email"
            type="email"
            autoComplete="username webauthn"
            inputMode="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
            aria-invalid={!!fieldErrors.email}
            aria-describedby={fieldErrors.email ? 'login-email-error' : undefined}
            placeholder={t('local.emailPlaceholder')}
          />
          {fieldErrors.email && (
            <p id="login-email-error" className="text-sm text-destructive">
              {t(fieldErrors.email)}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="login-password">{t('local.password')}</Label>
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            aria-invalid={!!fieldErrors.password}
            aria-describedby={fieldErrors.password ? 'login-password-error' : undefined}
          />
          {fieldErrors.password && (
            <p id="login-password-error" className="text-sm text-destructive">
              {t(fieldErrors.password)}
            </p>
          )}
        </div>
        <Button type="submit" className="w-full" size="lg" disabled={busy}>
          {pending === 'password' ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('signingIn')}
            </>
          ) : (
            t('local.submit')
          )}
        </Button>
      </form>

      <div className="flex items-center gap-3" aria-hidden="true">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs uppercase text-muted-foreground">{t('local.or')}</span>
        <div className="h-px flex-1 bg-border" />
      </div>

      <div className="space-y-2">
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          onClick={handlePasskey}
          disabled={busy || (support !== null && support !== 'supported')}
          aria-describedby={support && support !== 'supported' ? 'passkey-unavailable' : undefined}
        >
          {pending === 'passkey' ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Fingerprint className="mr-2 h-4 w-4" />
          )}
          {pending === 'passkey' ? t('passkey.waiting') : t('passkey.signIn')}
        </Button>
        {support && support !== 'supported' && (
          <p id="passkey-unavailable" className="text-center text-xs text-muted-foreground">
            {t(support === 'insecure' ? 'passkey.insecure' : 'passkey.unsupported')}
          </p>
        )}
      </div>

      {showOidc && <OIDCLoginButton getCallbackUrl={getCallbackUrl} />}
    </div>
  );
}

type ForwardSignInState = 'idle' | 'signingIn' | 'failed';
type ForwardFailure = 'headers' | 'server' | 'conflict' | 'usernameConflict';

const FORWARD_FAILURE_MESSAGES = {
  headers: 'forwardAuth.headersMissing',
  server: 'forwardAuth.serverError',
  conflict: 'forwardAuth.accountConflict',
  usernameConflict: 'forwardAuth.usernameConflict',
} as const;

function forwardFailureFor(errorCode: string | null | undefined): ForwardFailure {
  if (errorCode === FORWARD_AUTH_SERVER_ERROR) return 'server';
  if (errorCode === FORWARD_AUTH_ACCOUNT_CONFLICT) return 'conflict';
  if (errorCode === FORWARD_AUTH_USERNAME_CONFLICT) return 'usernameConflict';
  return 'headers';
}

// Lives in LoginContent rather than ForwardLogin so that the one-shot guard survives the
// skeleton swapping ForwardLogin out while the session reloads.
function useForwardSignIn(auto: boolean) {
  const [state, setState] = useState<ForwardSignInState>('idle');
  const [failure, setFailure] = useState<ForwardFailure | null>(null);
  const attempted = useRef(false);

  const signInThroughProxy = useCallback(async () => {
    setState('signingIn');
    // redirect: false keeps a failure on this page; a redirect would go through
    // pages.error ('/login?error=...') and lose the reason.
    const result = await signIn('forward-auth', { redirect: false });
    if (!result?.ok || result.error) {
      setFailure(forwardFailureFor(result?.error));
      setState('failed');
      return;
    }
    // Success normally ends on the redirect effect, which waits for an accessToken. A logout or
    // proxy user switch in another tab can clear the new cookie first, and the button must not
    // stay disabled then.
    const session = await getSession();
    if (!session?.accessToken) setState('idle');
  }, []);

  useEffect(() => {
    if (!auto || attempted.current) return;
    attempted.current = true;
    void signInThroughProxy();
  }, [auto, signInThroughProxy]);

  return { state, failure, signInThroughProxy };
}

function ForwardLogin({
  state,
  failure,
  loggedOut,
  onSignIn,
}: {
  state: ForwardSignInState;
  failure: ForwardFailure | null;
  loggedOut: boolean;
  onSignIn: () => void;
}) {
  const t = useTranslations('auth');

  return (
    <div className="space-y-4">
      {failure && state !== 'signingIn' && (
        <div className="rounded-md bg-destructive/15 p-4 text-sm text-destructive">
          {t(FORWARD_FAILURE_MESSAGES[failure])}
        </div>
      )}
      {loggedOut && !failure && state === 'idle' && (
        <p className="text-center text-sm text-muted-foreground">{t('forwardAuth.signedOut')}</p>
      )}
      <button
        type="button"
        onClick={onSignIn}
        disabled={state === 'signingIn'}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {state === 'signingIn' ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('signingIn')}
          </>
        ) : (
          t('forwardAuth.continue')
        )}
      </button>
    </div>
  );
}

function BackendError({ message }: { message: string }) {
  const t = useTranslations('auth');

  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm space-y-2">
      <p className="font-medium text-destructive">{t('backendError.title')}</p>
      <p className="text-destructive/90">{message}</p>
    </div>
  );
}

function LoginContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: session, status } = useSession();
  const error = searchParams.get('error');
  const syncErrorParam = searchParams.get('syncError');
  const loggedOut = searchParams.get('loggedOut') === '1';
  const callbackParam = searchParams.get('callbackUrl');
  // Resolved on use rather than during render, because the page is server-rendered too and
  // the same-origin check needs window.location.
  const getCallbackUrl = useCallback(
    () => safeCallbackUrl(callbackParam, window.location.origin),
    [callbackParam]
  );
  const [backendError, setBackendError] = useState<string | null>(null);
  const t = useTranslations('auth');

  useEffect(() => {
    if (status === 'authenticated' && session?.accessToken) {
      router.push(getCallbackUrl());
    }
  }, [status, session?.accessToken, getCallbackUrl, router]);

  // Check backend auth configuration on mount
  useEffect(() => {
    fetch(`${API_BASE_PATH}/auth/status`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.configured && data.error) {
          setBackendError(data.error);
        }
      })
      .catch(() => {
        setBackendError(t('backendError.description'));
      });
  }, [t]);

  const syncError = syncErrorParam || session?.syncError;

  const [providerMode, setProviderMode] = useState<'loading' | 'oidc' | 'dev' | 'unconfigured'>('loading');
  const authConfig = useAuthConfig();

  useEffect(() => {
    getProviders().then((providers) => {
      if (providers?.['oidc']) {
        setProviderMode('oidc');
      } else if (providers?.['dev-credentials']) {
        setProviderMode('dev');
      } else {
        setProviderMode('unconfigured');
      }
    });
  }, []);

  const authMode = authConfig.isPending
    ? 'loading'
    : authConfig.data?.forward_auth
      ? 'forward'
      : authConfig.data?.local_auth
        ? providerMode === 'loading'
          ? 'loading'
          : 'local'
        : providerMode;

  // A fresh install has no account to sign in to, so the first visit goes to /setup.
  useEffect(() => {
    if (authMode !== 'local') return;
    let cancelled = false;
    fetch(`${API_BASE_PATH}/auth/setup`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { required?: boolean } | null) => {
        if (!cancelled && data?.required) router.replace('/setup');
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [authMode, router]);

  const forward = useForwardSignIn(
    authMode === 'forward' && status === 'unauthenticated' && !error && !loggedOut
  );

  if (status === 'loading' || authMode === 'loading') {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-12 bg-muted rounded-md" />
      </div>
    );
  }

  return (
    <>
      {backendError && <BackendError message={backendError} />}

      {!backendError && syncError && <BackendError message={syncError} />}

      {error && authMode !== 'forward' && !backendError && !syncError && (
        <div className="rounded-md bg-destructive/15 p-4 text-sm text-destructive">
          {error === 'OAuthSignin' && t('errors.OAuthSignin')}
          {error === 'OAuthCallback' && t('errors.OAuthCallback')}
          {error === 'OAuthCreateAccount' && t('errors.OAuthCreateAccount')}
          {error === 'Callback' && t('errors.Callback')}
          {error === 'CredentialsSignin' && t('errors.CredentialsSignin')}
          {error === 'AccessDenied' && t('errors.AccessDenied')}
          {error === 'undefined' && t('errors.notConfigured')}
          {!['OAuthSignin', 'OAuthCallback', 'OAuthCreateAccount', 'Callback', 'CredentialsSignin', 'AccessDenied', 'undefined'].includes(error) && t('errors.default')}
        </div>
      )}

      <div className="space-y-4">
        {authMode === 'forward' && (
          <ForwardLogin
            state={forward.state}
            failure={
              forward.state === 'failed' ? forward.failure : error ? forwardFailureFor(error) : null
            }
            loggedOut={loggedOut}
            onSignIn={forward.signInThroughProxy}
          />
        )}
        {authMode === 'local' && (
          <LocalLogin showOidc={providerMode === 'oidc'} getCallbackUrl={getCallbackUrl} />
        )}
        {authMode === 'oidc' && <OIDCLoginButton getCallbackUrl={getCallbackUrl} />}
        {authMode === 'dev' && <DevLogin getCallbackUrl={getCallbackUrl} />}
        {authMode === 'unconfigured' && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm space-y-2">
            <p className="font-medium text-destructive">{t('unconfigured.title')}</p>
            <p className="text-destructive/90">
              {t.rich('unconfigured.description', {
                code: (chunks) => <code className="font-mono">{chunks}</code>,
              })}
            </p>
          </div>
        )}
      </div>
    </>
  );
}

export default function LoginPage() {
  const t = useTranslations('auth');

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="flex justify-center mb-4">
            <img src="/logo.svg" alt="Wardrowbe" className="h-16 w-16" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="mt-2 text-muted-foreground">
            {t('subtitle')}
          </p>
        </div>

        <Suspense fallback={<div className="space-y-4 animate-pulse"><div className="h-12 bg-muted rounded-md" /></div>}>
          <LoginContent />
        </Suspense>

        <p className="text-center text-sm text-muted-foreground">
          {t('termsAgreement')}
        </p>
      </div>
    </main>
  );
}
