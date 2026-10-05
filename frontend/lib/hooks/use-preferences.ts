'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import { Preferences } from '@/lib/types';

export function usePreferences() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['preferences'],
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
      queryClient.invalidateQueries({ queryKey: ['preferences'] });
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
      queryClient.invalidateQueries({ queryKey: ['preferences'] });
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
