'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { signIn } from 'next-auth/react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { API_BASE_PATH } from '@/lib/api';

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+$/;
const PASSWORD_MIN_LENGTH = 8;

type Field = 'email' | 'password' | 'confirm';
type SetupError = 'emailRequired' | 'emailInvalid' | 'passwordShort' | 'passwordMismatch';

export default function SetupPage() {
  const t = useTranslations('auth');
  const router = useRouter();
  const [state, setState] = useState<'checking' | 'ready' | 'saving'>('checking');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, SetupError>>>({});
  const [error, setError] = useState<'setup.alreadyDone' | 'setup.failed' | null>(null);

  // /setup only works while the instance has no account; afterwards it sends people to sign in.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_PATH}/auth/setup`)
      .then((res) => (res.ok ? res.json() : { required: false }))
      .then((data: { required?: boolean }) => {
        if (cancelled) return;
        if (data.required) setState('ready');
        else router.replace('/login');
      })
      .catch(() => {
        if (!cancelled) router.replace('/login');
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    const errors: Partial<Record<Field, SetupError>> = {};
    if (!trimmed) errors.email = 'emailRequired';
    else if (!EMAIL_PATTERN.test(trimmed)) errors.email = 'emailInvalid';
    if (password.length < PASSWORD_MIN_LENGTH) errors.password = 'passwordShort';
    if (confirm !== password) errors.confirm = 'passwordMismatch';
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setState('saving');
    const response = await fetch(`${API_BASE_PATH}/auth/setup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: trimmed, password, display_name: name.trim() || null }),
    }).catch(() => null);

    if (!response || !response.ok) {
      setError(response?.status === 409 ? 'setup.alreadyDone' : 'setup.failed');
      if (response?.status === 422) setFieldErrors({ email: 'emailInvalid' });
      setState('ready');
      return;
    }
    const result = await signIn('password', { email: trimmed, password, redirect: false });
    router.replace(result?.ok && !result.error ? '/dashboard' : '/login');
  };

  if (state === 'checking') {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" aria-label={t('setup.checking')} />
      </main>
    );
  }

  const saving = state === 'saving';
  const fieldError = (field: Field) =>
    fieldErrors[field] ? (
      <p id={`setup-${field}-error`} className="text-sm text-destructive">
        {t(`setup.errors.${fieldErrors[field]}`)}
      </p>
    ) : null;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="flex justify-center mb-4">
            <img src="/logo.svg" alt="Wardrowbe" className="h-16 w-16" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{t('setup.title')}</h1>
          <p className="mt-2 text-muted-foreground">{t('setup.subtitle')}</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md bg-destructive/15 p-4 text-sm text-destructive">
            {t(error)}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-4" aria-busy={saving}>
          <div className="space-y-2">
            <Label htmlFor="setup-name">{t('displayName')}</Label>
            <Input
              id="setup-name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={saving}
              placeholder={t('namePlaceholder')}
              maxLength={100}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-email">{t('email')}</Label>
            <Input
              id="setup-email"
              type="email"
              autoComplete="username"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={saving}
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? 'setup-email-error' : undefined}
            />
            {fieldError('email')}
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-password">{t('local.password')}</Label>
            <Input
              id="setup-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={saving}
              aria-invalid={!!fieldErrors.password}
              aria-describedby="setup-password-hint"
            />
            <p id="setup-password-hint" className="text-xs text-muted-foreground">
              {t('setup.passwordHint', { min: PASSWORD_MIN_LENGTH })}
            </p>
            {fieldError('password')}
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-confirm">{t('setup.confirmPassword')}</Label>
            <Input
              id="setup-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              disabled={saving}
              aria-invalid={!!fieldErrors.confirm}
              aria-describedby={fieldErrors.confirm ? 'setup-confirm-error' : undefined}
            />
            {fieldError('confirm')}
          </div>
          <Button type="submit" size="lg" className="w-full" disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="mr-2 h-4 w-4" />
            )}
            {t('setup.submit')}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">{t('setup.adminNote')}</p>
      </div>
    </main>
  );
}
