'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';
import {
  PairingListResponse,
  GeneratePairingsResponse,
} from '@/lib/types';

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function usePairings(page = 1, pageSize = 20, sourceType?: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['pairings', page, pageSize, sourceType],
    queryFn: async () => {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      if (sourceType) {
        params.source_type = sourceType;
      }
      return api.get<PairingListResponse>('/pairings', { params });
    },
    enabled: status !== 'loading',
  });
}

export function useItemPairings(itemId: string, page = 1, pageSize = 20) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['pairings', 'item', itemId, page, pageSize],
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
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<GeneratePairingsResponse>(`/pairings/generate/${itemId}`, {
        num_pairings: numPairings,
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      queryClient.invalidateQueries({ queryKey: ['pairings', 'item', variables.itemId] });
    },
  });
}

export function useDeletePairing() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (pairingId: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.delete(`/pairings/${pairingId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
    },
  });
}
