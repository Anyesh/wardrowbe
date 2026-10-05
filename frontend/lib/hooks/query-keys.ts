import type { ItemFilter } from '@/lib/types';
import type { OutfitFilters } from '@/lib/hooks/use-outfits';

// Invariant: the optimistic updaters call setQueriesData on queryKeys.items.all and
// queryKeys.outfits.all and assume every cache entry under those prefixes is a list response,
// so a single-item or single-outfit key must never be nested under ['items'] or ['outfits'].
const ITEMS = ['items'] as const;
const OUTFITS = ['outfits'] as const;
const CALENDAR_OUTFITS = ['calendarOutfits'] as const;
const PENDING_OUTFITS = ['pendingOutfits'] as const;
const FAMILY_OUTFITS = ['familyOutfits'] as const;
const ANALYTICS = ['analytics'] as const;
const LEARNING = ['learning'] as const;
const PAIRINGS = ['pairings'] as const;

export const queryKeys = {
  authConfig: ['auth-config'] as const,
  authUser: ['auth-user'] as const,
  userProfile: ['user-profile'] as const,
  features: ['features'] as const,
  weather: ['weather'] as const,
  preferences: ['preferences'] as const,
  family: ['family'] as const,

  items: {
    all: ITEMS,
    list: (filters: ItemFilter, page: number, pageSize: number) =>
      [...ITEMS, filters, page, pageSize] as const,
  },
  item: (itemId: string) => ['item', itemId] as const,
  itemTypes: ['item-types'] as const,
  colorDistribution: ['color-distribution'] as const,
  taggingProgress: ['tagging-progress'] as const,
  washHistory: (itemId: string) => ['wash-history', itemId] as const,
  wearStats: (itemId: string) => ['wear-stats', itemId] as const,
  wearHistory: (itemId: string) => ['wear-history', itemId] as const,

  outfits: {
    all: OUTFITS,
    list: (filters: OutfitFilters, page: number, pageSize: number) =>
      [...OUTFITS, filters, page, pageSize] as const,
  },
  outfit: (outfitId: string | undefined) => ['outfit', outfitId] as const,
  calendarOutfits: {
    all: CALENDAR_OUTFITS,
    month: (year: number, month: number, filters: OutfitFilters) =>
      [...CALENDAR_OUTFITS, year, month, filters] as const,
  },
  pendingOutfits: {
    all: PENDING_OUTFITS,
    list: (limit: number) => [...PENDING_OUTFITS, limit] as const,
  },
  familyOutfits: {
    all: FAMILY_OUTFITS,
    list: (memberId: string | undefined, page: number, pageSize: number) =>
      [...FAMILY_OUTFITS, memberId, page, pageSize] as const,
  },
  familyRatings: (outfitId: string | undefined) => ['familyRatings', outfitId] as const,

  analytics: {
    all: ANALYTICS,
    summary: (days: number) => [...ANALYTICS, days] as const,
  },
  learning: {
    all: LEARNING,
    itemPairs: (itemId: string, limit: number) =>
      [...LEARNING, 'item-pairs', itemId, limit] as const,
  },
  pairings: {
    all: PAIRINGS,
    list: (pageSize: number, sourceType: string | undefined) =>
      [...PAIRINGS, 'list', pageSize, sourceType] as const,
    forItem: (itemId: string) => [...PAIRINGS, 'item', itemId] as const,
    forItemPage: (itemId: string, page: number, pageSize: number) =>
      [...PAIRINGS, 'item', itemId, page, pageSize] as const,
  },

  notificationSettings: ['notification-settings'] as const,
  schedules: ['schedules'] as const,
  notificationHistory: (limit: number) => ['notification-history', limit] as const,
};
