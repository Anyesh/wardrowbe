'use client';

import { useEffect, useState } from 'react';
import { Fingerprint, KeyRound, Loader2, LogOut, Pencil, ShieldCheck, Trash2, UserPlus } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { ApiError, getErrorMessage } from '@/lib/api';
import {
  type Passkey,
  useChangePassword,
  useCreateLocalAccount,
  useDeletePasskey,
  useLocalAccounts,
  useRegisterPasskey,
  useRenamePasskey,
  useSecurityOverview,
} from '@/lib/hooks/use-security';
import { PasskeyCeremonyError, passkeySupport, suggestedPasskeyName } from '@/lib/passkeys';

const PASSWORD_MIN_LENGTH = 8;

type PendingAction =
  | { kind: 'addPasskey'; name: string }
  | { kind: 'deletePasskey'; passkey: Passkey }
  | null;

function useFormattedDate() {
  return (value: string | null) =>
    value ? new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' }) : null;
}

function ConfirmPasswordDialog({
  open,
  title,
  description,
  confirmLabel,
  destructive,
  needsPassword,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  needsPassword: boolean;
  pending: boolean;
  error: string | null;
  onConfirm: (password: string) => void;
  onClose: () => void;
}) {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const [password, setPassword] = useState('');

  useEffect(() => {
    if (!open) setPassword('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !pending && onClose()}>
      <DialogContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (needsPassword && !password) return;
            onConfirm(password);
          }}
          className="space-y-4"
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {needsPassword && (
            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t('security.currentPassword')}</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="current-password"
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={pending}
              />
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              {tc('cancel')}
            </Button>
            <Button
              type="submit"
              variant={destructive ? 'destructive' : 'default'}
              disabled={pending || (needsPassword && !password)}
            >
              {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PasswordForm({ hasPassword }: { hasPassword: boolean }) {
  const t = useTranslations('settings');
  const changePassword = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < PASSWORD_MIN_LENGTH) {
      setError(t('security.passwordTooShort', { min: PASSWORD_MIN_LENGTH }));
      return;
    }
    if (next !== confirm) {
      setError(t('security.passwordMismatch'));
      return;
    }
    try {
      await changePassword.mutateAsync({
        current_password: hasPassword ? current : undefined,
        new_password: next,
      });
      setCurrent('');
      setNext('');
      setConfirm('');
      toast.success(t('security.passwordChanged'));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? t('security.wrongPassword')
          : getErrorMessage(err, t('security.genericError'))
      );
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-3">
        {hasPassword && (
          <div className="space-y-2">
            <Label htmlFor="current-password">{t('security.currentPassword')}</Label>
            <Input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
        )}
        <div className="space-y-2">
          <Label htmlFor="new-password">{t('security.newPassword')}</Label>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm-new-password">{t('security.confirmPassword')}</Label>
          <Input
            id="confirm-new-password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <p className="text-xs text-muted-foreground">{t('security.passwordChangeNote')}</p>
      <Button
        type="submit"
        size="sm"
        disabled={changePassword.isPending || !next || (hasPassword && !current)}
      >
        {changePassword.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <KeyRound className="mr-2 h-4 w-4" />
        )}
        {hasPassword ? t('security.changePassword') : t('security.setPassword')}
      </Button>
    </form>
  );
}

function PasskeyRow({ passkey, onDelete }: { passkey: Passkey; onDelete: () => void }) {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const formatDate = useFormattedDate();
  const rename = useRenamePasskey();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(passkey.name);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === passkey.name) {
      setEditing(false);
      setName(passkey.name);
      return;
    }
    try {
      await rename.mutateAsync({ id: passkey.id, name: trimmed });
      setEditing(false);
    } catch (err) {
      toast.error(getErrorMessage(err, t('security.genericError')));
    }
  };

  const lastUsed = formatDate(passkey.last_used_at);

  return (
    <li className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <Fingerprint className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
              className="flex gap-2"
            >
              <Input
                aria-label={t('security.passkeyName')}
                value={name}
                maxLength={64}
                autoFocus
                onChange={(e) => setName(e.target.value)}
                className="h-8"
              />
              <Button type="submit" size="sm" disabled={rename.isPending}>
                {tc('save')}
              </Button>
            </form>
          ) : (
            <p className="truncate font-medium">{passkey.name}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {t('security.passkeyCreated', { date: formatDate(passkey.created_at) ?? '' })}
            {' · '}
            {lastUsed ? t('security.passkeyLastUsed', { date: lastUsed }) : t('security.passkeyNeverUsed')}
          </p>
          {passkey.backed_up && (
            <Badge variant="secondary" className="mt-1">
              {t('security.passkeySynced')}
            </Badge>
          )}
        </div>
      </div>
      {!editing && (
        <div className="flex gap-1 self-end sm:self-auto">
          <Button variant="ghost" size="icon" onClick={() => setEditing(true)} aria-label={t('security.renamePasskey')}>
            <Pencil className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDelete} aria-label={t('security.deletePasskey')}>
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      )}
    </li>
  );
}

function AccountsSection() {
  const t = useTranslations('settings');
  const accounts = useLocalAccounts(true);
  const create = useCreateLocalAccount();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCreate = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim() || password.length < PASSWORD_MIN_LENGTH) {
      setError(t('security.passwordTooShort', { min: PASSWORD_MIN_LENGTH }));
      return;
    }
    setConfirming(true);
  };

  const confirmCreate = async (currentPassword: string) => {
    try {
      await create.mutateAsync({
        email: email.trim(),
        display_name: name.trim() || undefined,
        password,
        is_admin: isAdmin,
        current_password: currentPassword,
      });
      toast.success(t('security.accountCreated', { email: email.trim() }));
      setEmail('');
      setName('');
      setPassword('');
      setIsAdmin(false);
      setConfirming(false);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? t('security.wrongPassword')
          : err instanceof ApiError && err.status === 409
            ? t('security.accountExists')
            : getErrorMessage(err, t('security.genericError'))
      );
      setConfirming(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="font-medium">{t('security.accountsTitle')}</h3>
        <p className="text-sm text-muted-foreground">{t('security.accountsDescription')}</p>
      </div>
      {accounts.data && (
        <ul className="space-y-1 text-sm">
          {accounts.data.map((account) => (
            <li key={account.id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{account.display_name}</span>
              <span className="text-muted-foreground">{account.email}</span>
              {account.is_admin && <Badge variant="outline">{t('security.adminBadge')}</Badge>}
              {!account.has_password && <Badge variant="secondary">{t('security.noPasswordBadge')}</Badge>}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={startCreate} className="space-y-3" noValidate>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="new-account-email">{t('account.email')}</Label>
            <Input
              id="new-account-email"
              type="email"
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-account-name">{t('account.name')}</Label>
            <Input id="new-account-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-account-password">{t('security.initialPassword')}</Label>
            <Input
              id="new-account-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="new-account-admin" checked={isAdmin} onCheckedChange={setIsAdmin} />
          <Label htmlFor="new-account-admin">{t('security.makeAdmin')}</Label>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" size="sm" variant="outline" disabled={!email || !password}>
          <UserPlus className="mr-2 h-4 w-4" />
          {t('security.createAccount')}
        </Button>
      </form>
      <ConfirmPasswordDialog
        open={confirming}
        title={t('security.createAccount')}
        description={t('security.confirmIdentity')}
        confirmLabel={t('security.createAccount')}
        needsPassword
        pending={create.isPending}
        error={null}
        onConfirm={confirmCreate}
        onClose={() => setConfirming(false)}
      />
    </div>
  );
}

export function AccountSecurity() {
  const t = useTranslations('settings');
  const overview = useSecurityOverview();
  const register = useRegisterPasskey();
  const remove = useDeletePasskey();
  const [newName, setNewName] = useState('');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [support, setSupport] = useState<ReturnType<typeof passkeySupport> | null>(null);

  useEffect(() => {
    setSupport(passkeySupport());
    setNewName(suggestedPasskeyName());
  }, []);

  const data = overview.data;
  if (!data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            {t('security.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label={t('security.loading')} />
        </CardContent>
      </Card>
    );
  }

  const needsPassword = data.has_password;

  const passkeyError = (err: unknown) => {
    if (err instanceof PasskeyCeremonyError) {
      if (err.reason === 'cancelled') return t('security.passkeyCancelled');
      if (err.reason === 'duplicate') return t('security.passkeyDuplicate');
      if (err.reason === 'insecure') return t('security.passkeyInsecure');
      if (err.reason === 'unsupported') return t('security.passkeyUnsupported');
    }
    if (err instanceof ApiError && err.status === 403) {
      return needsPassword ? t('security.wrongPassword') : t('security.signInAgain');
    }
    return getErrorMessage(err, t('security.genericError'));
  };

  const confirm = async (password: string) => {
    if (!pendingAction) return;
    setDialogError(null);
    try {
      if (pendingAction.kind === 'addPasskey') {
        await register.mutateAsync({ name: pendingAction.name, currentPassword: password });
        toast.success(t('security.passkeyAdded'));
        setNewName(suggestedPasskeyName());
      } else {
        await remove.mutateAsync({ id: pendingAction.passkey.id, currentPassword: password });
        toast.success(t('security.passkeyDeleted'));
      }
      setPendingAction(null);
    } catch (err) {
      setDialogError(passkeyError(err));
    }
  };

  const closeDialog = () => {
    setPendingAction(null);
    setDialogError(null);
  };

  const handleLogout = () => {
    // /auth/logout clears the session cookie server-side and ends any proxy or SSO session too.
    window.location.assign('/auth/logout');
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          {t('security.title')}
        </CardTitle>
        <CardDescription>{t('security.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-1">
          <Label>{t('account.email')}</Label>
          <p className="text-sm">{data.email}</p>
        </div>

        {data.local_auth_enabled && (
          <section className="space-y-3" aria-labelledby="security-password">
            <h3 id="security-password" className="font-medium">
              {t('security.passwordTitle')}
            </h3>
            <PasswordForm hasPassword={data.has_password} />
          </section>
        )}

        {data.local_auth_enabled && (
          <section className="space-y-3" aria-labelledby="security-passkeys">
            <div>
              <h3 id="security-passkeys" className="font-medium">
                {t('security.passkeysTitle')}
              </h3>
              <p className="text-sm text-muted-foreground">{t('security.passkeysDescription')}</p>
            </div>
            {data.passkeys.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('security.noPasskeys')}</p>
            ) : (
              <ul className="space-y-2">
                {data.passkeys.map((passkey) => (
                  <PasskeyRow
                    key={passkey.id}
                    passkey={passkey}
                    onDelete={() => setPendingAction({ kind: 'deletePasskey', passkey })}
                  />
                ))}
              </ul>
            )}
            <form
              className="flex flex-col gap-2 sm:flex-row sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                const name = newName.trim();
                if (name) setPendingAction({ kind: 'addPasskey', name });
              }}
            >
              <div className="flex-1 space-y-2">
                <Label htmlFor="new-passkey-name">{t('security.passkeyName')}</Label>
                <Input
                  id="new-passkey-name"
                  value={newName}
                  maxLength={64}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={t('security.passkeyNamePlaceholder')}
                  disabled={support !== null && support !== 'supported'}
                />
              </div>
              <Button
                type="submit"
                disabled={!newName.trim() || register.isPending || (support !== null && support !== 'supported')}
              >
                <Fingerprint className="mr-2 h-4 w-4" />
                {t('security.addPasskey')}
              </Button>
            </form>
            {support && support !== 'supported' && (
              <p className="text-sm text-muted-foreground">
                {support === 'insecure' ? t('security.passkeyInsecure') : t('security.passkeyUnsupported')}
              </p>
            )}
          </section>
        )}

        {data.local_auth_enabled && data.is_admin && <AccountsSection />}

        <div className="border-t pt-4">
          <Button variant="outline" onClick={handleLogout}>
            <LogOut className="mr-2 h-4 w-4" />
            {t('security.signOut')}
          </Button>
        </div>
      </CardContent>

      <ConfirmPasswordDialog
        open={pendingAction !== null}
        title={
          pendingAction?.kind === 'deletePasskey' ? t('security.deletePasskey') : t('security.addPasskey')
        }
        description={
          pendingAction?.kind === 'deletePasskey'
            ? t('security.deletePasskeyConfirm', { name: pendingAction.passkey.name })
            : needsPassword
              ? t('security.confirmIdentity')
              : t('security.addPasskeyNoPassword')
        }
        confirmLabel={
          pendingAction?.kind === 'deletePasskey' ? t('security.deletePasskey') : t('security.continue')
        }
        destructive={pendingAction?.kind === 'deletePasskey'}
        needsPassword={needsPassword}
        pending={register.isPending || remove.isPending}
        error={dialogError}
        onConfirm={confirm}
        onClose={closeDialog}
      />
    </Card>
  );
}
