'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';

export interface AIStatus {
  status: 'online' | 'model_missing' | 'offline' | 'disabled';
  vision_model: string | null;
  text_model: string | null;
  missing_models: string[];
}

export function useAIStatus() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.aiStatus,
    queryFn: () => api.get<AIStatus>('/ai/status'),
    enabled: status === 'authenticated',
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}
