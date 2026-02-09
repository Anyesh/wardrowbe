'use client';

import { Suspense, useEffect, useState } from 'react';
import { signIn, getProviders, useSession } from 'next-auth/react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

function OIDCLoginButton({ callbackUrl }: { callbackUrl: string }) {
  return (
    <button
      onClick={() => signIn('oidc', { callbackUrl })}
      className="flex w-full items-center justify-center gap-3 rounded-md bg-primary px-4 py-3 text-primary-foreground hover:bg-primary/90 transition-colors"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
      </svg>
      Sign in
    </button>
  );
}
function ForwardAuthLogin({ callbackUrl }: { callbackUrl: string }) {
  const router = useRouter();

  // In forward auth mode, user is already authenticated via TinyAuth/nginx.
  // Try to access the API directly - if it works, redirect to dashboard.
  useEffect(() => {
    async function checkForwardAuth() {
      try {
        const response = await fetch('/api/v1/users/me', { credentials: 'include' });
        if (response.ok) {
          // Already authenticated via forward auth, redirect to dashboard
          router.push(callbackUrl);
        }
      } catch {
        // Not authenticated or error, stay on login page
      }
    }
    checkForwardAuth();
  }, [callbackUrl, router]);

  return (
    <div className="text-center space-y-4">
      <div className="flex justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
      <p className="text-muted-foreground">
        Authenticating...
      </p>
      <p className="text-sm text-muted-foreground">
        If you&apos;re not redirected, please check your TinyAuth configuration.
      </p>
    </div>
  );
}

function DevLogin({ callbackUrl }: { callbackUrl: string }) {
  const [email, setEmail] = useState('dev@wardrobe.local');
  const [name, setName] = useState('Dev User');
  const [isLoading, setIsLoading] = useState(false);

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
        Development Mode - Any credentials accepted
      </div>
      <div className="space-y-2">
        <label htmlFor="email" className="block text-sm font-medium">
          Email
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
          Display Name
        </label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="Your Name"
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
            Signing in...
          </>
        ) : (
          'Sign in'
        )}
      </button>
    </form>
  );
}

function LoginContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { status } = useSession();
  const error = searchParams.get('error');
  const callbackUrl = searchParams.get('callbackUrl') || '/dashboard';

  // If already authenticated via NextAuth, redirect
  useEffect(() => {
    if (status === 'authenticated') {
      router.push(callbackUrl);
    }
  }, [status, callbackUrl, router]);

  // Detect auth mode based on available providers
  const [authMode, setAuthMode] = useState<'loading' | 'forward-auth' | 'oidc' | 'dev'>('loading');

  useEffect(() => {
    getProviders().then((providers) => {

      if (providers?.['oidc']) {
        setAuthMode('oidc');
      } else if (providers?.['dev-credentials']) {
        setAuthMode('dev');
      } else if (providers?.['forward-auth']) {
        setAuthMode('forward-auth');
      } else {
        // Fallback to dev mode
        setAuthMode('dev');
      }
    });
  }, []);

  if (status === 'loading' || authMode === 'loading') {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-12 bg-muted rounded-md" />
      </div>
    );
  }

  return (
    <>
      {error && (
        <div className="rounded-md bg-destructive/15 p-4 text-sm text-destructive">
          {error === 'OAuthSignin' && 'Error starting authentication'}
          {error === 'OAuthCallback' && 'Error during authentication callback'}
          {error === 'OAuthCreateAccount' && 'Error creating account'}
          {error === 'Callback' && 'Error during callback'}
          {error === 'CredentialsSignin' && 'Invalid credentials'}
          {error === 'AccessDenied' && 'Access denied'}
          {!['OAuthSignin', 'OAuthCallback', 'OAuthCreateAccount', 'Callback', 'CredentialsSignin', 'AccessDenied'].includes(error) && 'An error occurred during sign in'}
        </div>
      )}

      <div className="space-y-4">
        {authMode === 'oidc' && <OIDCLoginButton callbackUrl={callbackUrl} />}
        {authMode === 'forward-auth' && <ForwardAuthLogin callbackUrl={callbackUrl} />}
        {authMode === 'dev' && <DevLogin callbackUrl={callbackUrl} />}

      </div>
    </>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="flex justify-center mb-4">
            <img src="/logo.svg" alt="Wardrowbe" className="h-16 w-16" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">wardrowbe</h1>
          <p className="mt-2 text-muted-foreground">
            Sign in to manage your wardrobe
          </p>
        </div>

        <Suspense fallback={<div className="space-y-4 animate-pulse"><div className="h-12 bg-muted rounded-md" /></div>}>
          <LoginContent />
        </Suspense>

        <p className="text-center text-sm text-muted-foreground">
          By signing in, you agree to our terms of service and privacy policy.
        </p>
      </div>
    </main>
  );
}
