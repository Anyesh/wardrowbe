'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import type { Item } from '@/lib/types';

export interface SwapEntry {
  item: Item;
  reason: 'season' | 'last_year';
}

export interface SeasonSwap {
  current_season: string;
  upcoming_season: string;
  put_away: SwapEntry[];
  bring_out: SwapEntry[];
  stays: number;
}

export function useSeasonSwap() {
  const { data: session, status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    // Per account: another sign-in in the same tab never sees this one's clothes.
    queryKey: [...queryKeys.seasonSwap, session?.user?.id ?? ''],
    queryFn: () => api.get<SeasonSwap>('/season-swap'),
    enabled: status === 'authenticated',
    // Wears and edits elsewhere move items between the lists: fetch again on every visit.
    staleTime: 0,
    refetchOnMount: 'always',
  });
}
