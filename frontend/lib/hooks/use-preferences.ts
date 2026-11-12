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

export function useSetItemExcluded() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: ({ itemId, excluded }: { itemId: string; excluded: boolean }) => {
      applySessionToken(session);
      const path = `/users/me/preferences/excluded-items/${itemId}`;
      return excluded
        ? api.post<{ excluded_item_ids: string[] }>(path)
        : api.delete<{ excluded_item_ids: string[] }>(path);
    },
    // Settled, not success: if the response is lost after the server saved the change, the
    // switch must still reconcile with the stored state. Learned item pairs are recomputed
    // because they may list the item that was just excluded.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.preferences });
      queryClient.invalidateQueries({ queryKey: queryKeys.learning.all });
    },
  });
}

interface AITestResult {
  status: 'connected' | 'error';
  available_models?: string[];
  vision_models?: string[];
  text_models?: string[];
  error?: string;
}

export function useTestAIEndpoint() {
  const { data: session } = useSession();

  return useMutation({
    mutationFn: (url: string) => {
      applySessionToken(session);
      return api.post<AITestResult>('/users/me/preferences/test-ai-endpoint', { url });
    },
  });
}
