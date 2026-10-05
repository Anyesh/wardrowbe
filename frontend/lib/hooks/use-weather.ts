'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import type { CurrentWeather } from '@/lib/types';

export function useWeather() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['weather'],
    queryFn: () => api.get<CurrentWeather>('/weather/current'),
    enabled: status !== 'loading',
    staleTime: 1000 * 60 * 15, // 15 minutes - weather doesn't change that fast
    retry: false, // Don't retry if location not set
  });
}
