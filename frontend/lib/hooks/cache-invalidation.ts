import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/hooks/query-keys';

export function invalidateItemCaches(queryClient: QueryClient, itemId: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.items.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.item(itemId) });
}

// Outfit and calendar payloads embed each item's primary image, so they go
// stale whenever that image changes, not only the item caches.
export function invalidatePrimaryImageQueries(queryClient: QueryClient, itemId: string) {
  invalidateItemCaches(queryClient, itemId);
  queryClient.invalidateQueries({ queryKey: queryKeys.outfits.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.calendarOutfits.all });
}

export function invalidateOutfitCaches(queryClient: QueryClient, outfitId?: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.outfits.all });
  if (outfitId !== undefined) {
    queryClient.invalidateQueries({ queryKey: queryKeys.outfit(outfitId) });
  }
  queryClient.invalidateQueries({ queryKey: queryKeys.calendarOutfits.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.pendingOutfits.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.analytics.all });
}
