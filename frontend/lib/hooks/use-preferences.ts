'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import { Preferences } from '@/lib/types';
import { queryKeys } from '@/lib/hooks/query-keys';

export function usePreferences() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.preferences,
    queryFn: () => api.get<Preferences>('/users/me/preferences'),
    enabled: status !== 'loading',
  });
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: (data: Partial<Preferences>) => {
      applySessionToken(session);
      return api.patch<Preferences>('/users/me/preferences', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.preferences });
    },
  });
}

export function useResetPreferences() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: () => {
      applySessionToken(session);
      return api.post<Preferences>('/users/me/preferences/reset');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.preferences });
    },
  });
}

interface AITestResult {
  status: 'connected' | 'error';
  available_models?: string[];
  vision_models?: string[];
  text_models?: string[];
  error?: string;
  error_code?: string;
  params?: Record<string, string | number>;
}

export function useTestAIEndpoint() {
  const { data: session } = useSession();

  return useMutation({
    // Without a typed key (undefined) the server tests with the saved key of endpoint `id`, if the URL
    // still matches. An empty key, as after "Remove key", tests without one.
    mutationFn: ({ url, id, api_key }: { url: string; id?: string | null; api_key?: string }) => {
      applySessionToken(session);
      return api.post<AITestResult>('/users/me/preferences/test-ai-endpoint', {
        url,
        id: id ?? undefined,
        api_key,
      });
    },
  });
}
