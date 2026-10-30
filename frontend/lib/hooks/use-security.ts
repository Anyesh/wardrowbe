'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import type { PublicKeyCredentialCreationOptionsJSON } from '@simplewebauthn/browser';
import { api, setAccessToken } from '@/lib/api';
import { queryKeys } from '@/lib/hooks/query-keys';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { createPasskeyCredential } from '@/lib/passkeys';

export interface Passkey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  backed_up: boolean;
  transports: string[];
}

export interface SecurityOverview {
  email: string;
  local_auth_enabled: boolean;
  has_password: boolean;
  is_admin: boolean;
  passkeys: Passkey[];
}

export interface LocalAccount {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  has_password: boolean;
  created_at: string;
}

export function useSecurityOverview() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.security,
    queryFn: () => api.get<SecurityOverview>('/auth/security'),
    enabled: status === 'authenticated',
  });
}

export function useChangePassword() {
  const { update } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { current_password?: string; new_password: string }) =>
      api.post<{ access_token: string }>('/auth/password', data),
    onSuccess: async ({ access_token }) => {
      // The change ended every session's old token, this tab's included, so the new one replaces
      // it in memory at once and in the session cookie for the next page load.
      setAccessToken(access_token);
      await update({ accessToken: access_token });
      queryClient.invalidateQueries({ queryKey: queryKeys.security });
    },
  });
}

export function useRegisterPasskey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, currentPassword }: { name: string; currentPassword?: string }) => {
      const options = await api.post<PublicKeyCredentialCreationOptionsJSON>(
        '/auth/passkeys/register/options',
        { current_password: currentPassword || null }
      );
      const credential = await createPasskeyCredential(options);
      return api.post<Passkey>('/auth/passkeys/register/verify', { name, credential });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.security }),
  });
}

export function useRenamePasskey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch<Passkey>(`/auth/passkeys/${id}`, { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.security }),
  });
}

export function useDeletePasskey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, currentPassword }: { id: string; currentPassword?: string }) =>
      api.delete<void>(`/auth/passkeys/${id}`, {
        body: JSON.stringify({ current_password: currentPassword || null }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.security }),
  });
}

export function useLocalAccounts(enabled: boolean) {
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.localAccounts,
    queryFn: () => api.get<LocalAccount[]>('/auth/users'),
    enabled,
  });
}

export function useCreateLocalAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      email: string;
      display_name?: string;
      password: string;
      is_admin: boolean;
      current_password?: string;
    }) => api.post<LocalAccount>('/auth/users', data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.localAccounts }),
  });
}
