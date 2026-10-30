import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { invalidateItemCaches } from '@/lib/hooks/cache-invalidation';
import { queryKeys } from '@/lib/hooks/query-keys';
import { applySessionToken, useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import type { Box } from '@/lib/split-boxes';

export interface DetectedGarment extends Box {
  type: string;
  colors: string[];
}

interface DetectGarmentsResponse {
  garments: DetectedGarment[];
}

interface SplitResponse {
  source_id: string;
  item_ids: string[];
}

/** Asks the AI where the garments in an item's photo are. Creates nothing. */
export function useGarmentDetection(itemId: string, enabled: boolean) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.garmentDetection(itemId),
    // No abort signal: StrictMode's simulated unmount would cancel the POST and send it again.
    queryFn: () => api.post<DetectGarmentsResponse>(`/items/${itemId}/detect-garments`),
    enabled: enabled && status !== 'loading',
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    meta: { toastsOwnErrors: true },
  });
}

/** Makes one item per box from an item's photo and archives the original. */
export function useSplitItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ itemId, boxes }: { itemId: string; boxes: Box[] }) => {
      applySessionToken(session);
      return api.post<SplitResponse>(`/items/${itemId}/split`, {
        boxes: boxes.map(({ left, top, width, height }) => ({ left, top, width, height })),
      });
    },
    onSuccess: (_, variables) => {
      invalidateItemCaches(queryClient, variables.itemId);
      queryClient.invalidateQueries({ queryKey: queryKeys.taggingProgress });
    },
  });
}
