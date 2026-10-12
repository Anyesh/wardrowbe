'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import type { CurrentWeather } from '@/lib/types';
import { queryKeys } from '@/lib/hooks/query-keys';
import { WEATHER_STALE_TIME } from '@/lib/hooks/query-timing';

export function useWeather() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.weather,
    queryFn: () => api.get<CurrentWeather>('/weather/current'),
    enabled: status !== 'loading',
    staleTime: WEATHER_STALE_TIME,
    retry: false, // Don't retry if location not set
  });
}
