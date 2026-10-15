'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken, useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import type { Item } from '@/lib/types';

export interface DeclutterCandidate {
  item: Item;
  reason: 'never_worn' | 'not_worn_recently';
  idle_days: number;
}

export interface DeclutterReview {
  months: number;
  total_items: number;
  idle_value: string;
  candidates: DeclutterCandidate[];
}

export function useDeclutter(months: number) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.declutter(months),
    queryFn: () => api.get<DeclutterReview>(`/declutter?months=${months}`),
    enabled: status === 'authenticated',
  });
}

export function useKeepItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ id, months }: { id: string; months: number }) => {
      applySessionToken(session);
      return api.post<{ item_id: string; kept_until: string }>(`/declutter/${id}/keep`, {
        months,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.declutterAll });
    },
  });
}
