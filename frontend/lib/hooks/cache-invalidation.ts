import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/hooks/query-keys';

export function invalidateItemCaches(queryClient: QueryClient, itemId: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.items.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.item(itemId) });
}

export function invalidateItemWearCaches(queryClient: QueryClient, itemId: string) {
  invalidateItemCaches(queryClient, itemId);
  queryClient.invalidateQueries({ queryKey: queryKeys.wearStats.item(itemId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.wearHistory.item(itemId) });
}

// Wearing an outfit bumps the wear count of every item in it, and the client does not always
// hold those ids (feedback only names the outfit), so every item and wear cache goes stale.
export function invalidateEveryItemWearCache(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.items.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.everyItem });
  queryClient.invalidateQueries({ queryKey: queryKeys.wearStats.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.wearHistory.all });
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
