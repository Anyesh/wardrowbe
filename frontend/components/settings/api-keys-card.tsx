'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound, Loader2, Plus, ShieldOff } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { api, setAccessToken } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type ApiKeyScope = 'items:read' | 'items:write' | 'images:read';

interface ApiKeyRecord {
  id: string;
  name: string;
  scopes: ApiKeyScope[];
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

interface ApiKeyCreated extends ApiKeyRecord {
  token: string;
}

const SCOPE_OPTIONS: Array<{ value: ApiKeyScope; label: string }> = [
  { value: 'items:read', label: 'itemsRead' },
  { value: 'items:write', label: 'itemsWrite' },
  { value: 'images:read', label: 'imagesRead' },
];

export function ApiKeysCard() {
  const t = useTranslations('settings');
  const { data: session, status } = useSession();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<ApiKeyScope[]>(['items:read']);
  const [expiresAt, setExpiresAt] = useState('');
  const [createdToken, setCreatedToken] = useState<ApiKeyCreated | null>(null);

  const prepareAuth = () => {
    if (session?.accessToken) setAccessToken(session.accessToken as string);
  };

  const keysQuery = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => {
      prepareAuth();
      return api.get<ApiKeyRecord[]>('/auth/api-keys');
    },
    enabled: status !== 'loading',
  });

  const createKey = useMutation({
    mutationFn: () => {
      prepareAuth();
      return api.post<ApiKeyCreated>('/auth/api-keys', {
        name: name.trim(),
        scopes,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
    },
    onSuccess: (created) => {
      setCreatedToken(created);
      setShowCreate(false);
      setName('');
      setScopes(['items:read']);
      setExpiresAt('');
      void queryClient.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  const revokeKey = useMutation({
    mutationFn: (keyId: string) => {
      prepareAuth();
      return api.post<ApiKeyRecord>(`/auth/api-keys/${keyId}/revoke`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  const toggleScope = (scope: ApiKeyScope) => {
    setScopes((current) =>
      current.includes(scope) ? current.filter((value) => value !== scope) : [...current, scope]
    );
  };

  const copyToken = async () => {
    if (!createdToken) return;
    try {
      await navigator.clipboard.writeText(createdToken.token);
      toast.success(t('apiKeys.copied'));
    } catch {
      toast.error(t('apiKeys.copyFailed'));
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" />
              {t('apiKeys.title')}
            </CardTitle>
            <CardDescription>{t('apiKeys.description')}</CardDescription>
          </div>
          {!showCreate && (
            <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t('apiKeys.create')}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {createdToken && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 space-y-3">
            <p className="text-sm font-medium">{t('apiKeys.tokenCreated')}</p>
            <p className="text-sm text-muted-foreground">{t('apiKeys.tokenWarning')}</p>
            <code className="block break-all rounded bg-background p-3 text-sm">{createdToken.token}</code>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => void copyToken()}>
                <Copy className="mr-2 h-4 w-4" />
                {t('apiKeys.copy')}
              </Button>
              <Button size="sm" onClick={() => setCreatedToken(null)}>{t('apiKeys.done')}</Button>
            </div>
          </div>
        )}

        {showCreate && (
          <div className="rounded-lg border p-4 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api-key-name">{t('apiKeys.name')}</Label>
              <Input
                id="api-key-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t('apiKeys.namePlaceholder')}
                maxLength={100}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('apiKeys.scopesLabel')}</Label>
              <div className="grid gap-2 sm:grid-cols-3">
                {SCOPE_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-center gap-2 rounded border p-3 text-sm">
                    <input
                      type="checkbox"
                      checked={scopes.includes(option.value)}
                      onChange={() => toggleScope(option.value)}
                    />
                    {t(`apiKeys.scopes.${option.label}`)}
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-key-expiry">{t('apiKeys.expiresAt')}</Label>
              <Input
                id="api-key-expiry"
                type="datetime-local"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t('apiKeys.expiresOptional')}</p>
            </div>
            {createKey.isError && <p className="text-sm text-destructive">{t('apiKeys.createError')}</p>}
            <div className="flex gap-2">
              <Button
                onClick={() => createKey.mutate()}
                disabled={!name.trim() || scopes.length === 0 || createKey.isPending}
              >
                {createKey.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('apiKeys.createKey')}
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)} disabled={createKey.isPending}>
                {t('apiKeys.cancel')}
              </Button>
            </div>
          </div>
        )}

        {keysQuery.isLoading ? (
          <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : keysQuery.isError ? (
          <p className="text-sm text-destructive">{t('apiKeys.loadError')}</p>
        ) : (keysQuery.data?.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">{t('apiKeys.noKeys')}</p>
        ) : (
          <div className="space-y-3">
            {keysQuery.data?.map((key) => {
              const expired = Boolean(key.expires_at && new Date(key.expires_at) <= new Date());
              const inactive = Boolean(key.revoked_at) || expired;
              return (
                <div key={key.id} className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{key.name}</p>
                        <Badge variant={inactive ? 'secondary' : 'default'}>
                          {key.revoked_at ? t('apiKeys.revoked') : expired ? t('apiKeys.expired') : t('apiKeys.active')}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t('apiKeys.createdAt')}: {new Date(key.created_at).toLocaleString()}
                      </p>
                      {key.last_used_at && (
                        <p className="text-xs text-muted-foreground">
                          {t('apiKeys.lastUsed')}: {new Date(key.last_used_at).toLocaleString()}
                        </p>
                      )}
                      {key.expires_at && (
                        <p className="text-xs text-muted-foreground">
                          {t('apiKeys.expiresAt')}: {new Date(key.expires_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    {!key.revoked_at && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={revokeKey.isPending}
                        onClick={() => {
                          if (window.confirm(t('apiKeys.revokeConfirm', { name: key.name }))) {
                            revokeKey.mutate(key.id);
                          }
                        }}
                      >
                        <ShieldOff className="mr-2 h-4 w-4" />
                        {t('apiKeys.revoke')}
                      </Button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {key.scopes.map((scope) => <Badge key={scope} variant="outline">{scope}</Badge>)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
