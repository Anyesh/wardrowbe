'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken } from '@/lib/hooks/use-session-token';

interface Features {
  background_removal: boolean;
  max_upload_size_mb: number;
}

export function useFeatures() {
  const { data: session, status } = useSession();
  applySessionToken(session);

  return useQuery({
    queryKey: ['features'],
    queryFn: () => api.get<Features>('/health/features'),
    enabled: status !== 'loading',
    staleTime: 5 * 60 * 1000,
  });
}
