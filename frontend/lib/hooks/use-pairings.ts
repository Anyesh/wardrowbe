'use client';

import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import {
  Pairing,
  PairingListResponse,
  GeneratePairingsRequest,
  GeneratePairingsResponse,
} from '@/lib/types';
import { queryKeys } from '@/lib/hooks/query-keys';
import { DEFAULT_PAGE_SIZE } from '@/lib/pagination';

export function usePairings(pageSize = DEFAULT_PAGE_SIZE, sourceType?: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useInfiniteQuery({
    queryKey: queryKeys.pairings.list(pageSize, sourceType),
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string> = {
        page: String(pageParam),
        page_size: String(pageSize),
      };
      if (sourceType) {
        params.source_type = sourceType;
      }
      return api.get<PairingListResponse>('/pairings', { params });
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    enabled: status !== 'loading',
  });
}

export function useItemPairings(itemId: string, page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.pairings.forItemPage(itemId, page, pageSize),
    queryFn: async () => {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      return api.get<PairingListResponse>(`/pairings/item/${itemId}`, { params });
    },
    enabled: !!itemId && status !== 'loading',
  });
}

export function useGeneratePairings() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      itemId,
      numPairings = 3,
    }: {
      itemId: string;
      numPairings?: number;
    }) => {
      applySessionToken(session);
      return api.post<GeneratePairingsResponse>(`/pairings/generate/${itemId}`, {
        num_pairings: numPairings,
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pairings.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.pairings.forItem(variables.itemId) });
    },
  });
}

export function useDeletePairing() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (pairingId: string) => {
      applySessionToken(session);
      return api.delete(`/pairings/${pairingId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pairings.all });
    },
  });
}
