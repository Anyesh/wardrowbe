'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { signIn, getProviders, useSession } from 'next-auth/react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { API_BASE_PATH } from '@/lib/api';
import { FORWARD_AUTH_ACCOUNT_CONFLICT, FORWARD_AUTH_SERVER_ERROR } from '@/lib/auth-errors';
import { useAuthConfig } from '@/lib/hooks/use-auth-config';

function OIDCLoginButton({ callbackUrl }: { callbackUrl: string }) {
  const t = useTranslations('auth');

  return (
    <button
      onClick={() => signIn('oidc', { callbackUrl })}
      className="flex w-full items-center justify-center gap-3 rounded-md bg-primary px-4 py-3 text-primary-foreground hover:bg-primary/90 transition-colors"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
      </svg>
      {t('title')}
    </button>
  );
}

function DevLogin({ callbackUrl }: { callbackUrl: string }) {
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
      callbackUrl,
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

type ForwardSignInState = 'idle' | 'signingIn' | 'failed';
type ForwardFailure = 'headers' | 'server' | 'conflict';

const FORWARD_FAILURE_MESSAGES = {
  headers: 'forwardAuth.headersMissing',
  server: 'forwardAuth.serverError',
  conflict: 'forwardAuth.accountConflict',
} as const;

function forwardFailureFor(errorCode: string | null | undefined): ForwardFailure {
  if (errorCode === FORWARD_AUTH_SERVER_ERROR) return 'server';
  if (errorCode === FORWARD_AUTH_ACCOUNT_CONFLICT) return 'conflict';
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
    }
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
  const callbackUrl = searchParams.get('callbackUrl') || '/dashboard';
  const [backendError, setBackendError] = useState<string | null>(null);
  const t = useTranslations('auth');

  useEffect(() => {
    if (status === 'authenticated' && session?.accessToken) {
      router.push(callbackUrl);
    }
  }, [status, session?.accessToken, callbackUrl, router]);

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
      : providerMode;

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
        {authMode === 'oidc' && <OIDCLoginButton callbackUrl={callbackUrl} />}
        {authMode === 'dev' && <DevLogin callbackUrl={callbackUrl} />}
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
