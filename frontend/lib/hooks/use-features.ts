'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';

interface Features {
  background_removal: boolean;
}

export function useFeatures() {
  const { data: session, status } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }

  return useQuery({
    queryKey: ['features'],
    queryFn: () => api.get<Features>('/health/features'),
    enabled: status !== 'loading',
    staleTime: 5 * 60 * 1000,
  });
}
