import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import type { FamilyRating, Outfit, OutfitStatus } from '@/lib/types';
import { formatDateKey } from '@/lib/utils';
import { DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE } from '@/lib/pagination';
import { queryKeys } from '@/lib/hooks/query-keys';
import { invalidateOutfitCaches } from '@/lib/hooks/cache-invalidation';

export type {
  FeedbackSummary,
  Outfit,
  OutfitItem,
  OutfitSource,
  OutfitStatus,
  WeatherData,
  WoreInsteadItem,
} from '@/lib/types';

export interface OutfitListResponse {
  outfits: Outfit[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OutfitFilters {
  status?: OutfitStatus;
  occasion?: string;
  date_from?: string;
  date_to?: string;
  source?: string;
  is_lookbook?: boolean;
  is_replacement?: boolean;
  has_source_item?: boolean;
  search?: string;
  cloned_from_outfit_id?: string;
}

export interface FeedbackData {
  accepted?: boolean;
  rating?: number;
  comfort_rating?: number;
  style_rating?: number;
  comment?: string;
  worn?: boolean;
  worn_with_modifications?: boolean;
  modification_notes?: string;
  actually_worn?: boolean;
  wore_instead_items?: string[];
}

export interface FeedbackResponse {
  id: string;
  outfit_id: string;
  accepted: boolean | null;
  rating: number | null;
  comfort_rating: number | null;
  style_rating: number | null;
  comment: string | null;
  worn_at: string | null;
  worn_with_modifications: boolean;
  modification_notes: string | null;
  actually_worn: boolean | null;
  wore_instead_items: string[] | null;
  created_at: string;
}

function outfitListParams(filters: OutfitFilters, page: number, pageSize: number) {
  const params: Record<string, string> = {
    page: String(page),
    page_size: String(pageSize),
  };

  if (filters.status) params.status = filters.status;
  if (filters.occasion) params.occasion = filters.occasion;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.source) params.source = filters.source;
  if (filters.is_lookbook !== undefined) params.is_lookbook = String(filters.is_lookbook);
  if (filters.is_replacement !== undefined)
    params.is_replacement = String(filters.is_replacement);
  if (filters.has_source_item !== undefined)
    params.has_source_item = String(filters.has_source_item);
  if (filters.search) params.search = filters.search;
  if (filters.cloned_from_outfit_id)
    params.cloned_from_outfit_id = filters.cloned_from_outfit_id;

  return params;
}

export function useOutfits(filters: OutfitFilters = {}, page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.outfits.list(filters, page, pageSize),
    queryFn: () =>
      api.get<OutfitListResponse>('/outfits', {
        params: outfitListParams(filters, page, pageSize),
      }),
    enabled: status !== 'loading',
  });
}

export function useInfiniteOutfits(filters: OutfitFilters = {}, pageSize = DEFAULT_PAGE_SIZE) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useInfiniteQuery({
    queryKey: queryKeys.outfits.infinite(filters, pageSize),
    queryFn: ({ pageParam }) =>
      api.get<OutfitListResponse>('/outfits', {
        params: outfitListParams(filters, pageParam, pageSize),
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    enabled: status !== 'loading',
  });
}

type CachedOutfitList = OutfitListResponse | InfiniteData<OutfitListResponse, number>;

// Every entry under queryKeys.outfits.all is either a single page or the infinite list's pages,
// so the optimistic updaters must rewrite both shapes.
function mapCachedOutfitPages(
  cached: CachedOutfitList | undefined,
  update: (page: OutfitListResponse) => OutfitListResponse,
): CachedOutfitList | undefined {
  if (!cached) return cached;
  if ('pages' in cached) return { ...cached, pages: cached.pages.map(update) };
  return update(cached);
}

export function useOutfit(outfitId: string | undefined) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.outfit(outfitId),
    queryFn: () => api.get<Outfit>(`/outfits/${outfitId}`),
    enabled: !!outfitId && status !== 'loading',
  });
}

export function useAcceptOutfit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (outfitId: string) => api.post<Outfit>(`/outfits/${outfitId}/accept`),
    onSuccess: (_, outfitId) => {
      invalidateOutfitCaches(queryClient, outfitId);
    },
  });
}

export function useRejectOutfit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (outfitId: string) => api.post<Outfit>(`/outfits/${outfitId}/reject`),
    onSuccess: (_, outfitId) => {
      invalidateOutfitCaches(queryClient, outfitId);
    },
  });
}

export function useSubmitFeedback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ outfitId, feedback }: { outfitId: string; feedback: FeedbackData }) =>
      api.post<FeedbackResponse>(`/outfits/${outfitId}/feedback`, feedback),
    onSuccess: (_, { outfitId }) => {
      invalidateOutfitCaches(queryClient, outfitId);
    },
  });
}

export function useDeleteOutfit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (outfitId: string) => api.delete<void>(`/outfits/${outfitId}`),
    onSuccess: () => {
      invalidateOutfitCaches(queryClient);
    },
  });
}

export interface BulkDeleteOutfitsResponse {
  deleted: number;
  failed: number;
  errors: string[];
}

export interface BulkOutfitOperationParams {
  // Either provide explicit outfit_ids, or use select_all with excluded_ids
  outfit_ids?: string[];
  select_all?: boolean;
  excluded_ids?: string[];
  // Filters to apply when using select_all (to match the current view)
  filters?: OutfitFilters;
}

export function useBulkDeleteOutfits() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (params: BulkOutfitOperationParams) => {
      applySessionToken(session);
      return api.post<BulkDeleteOutfitsResponse>('/outfits/bulk/delete', params);
    },
    onMutate: async (params) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.outfits.all });

      const previousData = queryClient.getQueriesData({ queryKey: queryKeys.outfits.all });

      if (params.select_all) {
        const excludedSet = new Set(params.excluded_ids || []);
        queryClient.setQueriesData<CachedOutfitList>({ queryKey: queryKeys.outfits.all }, (old) =>
          mapCachedOutfitPages(old, (page) => ({
            ...page,
            outfits: page.outfits.filter((outfit) => excludedSet.has(outfit.id)),
            total: excludedSet.size,
          })),
        );
      } else if (params.outfit_ids) {
        const deletedSet = new Set(params.outfit_ids);
        queryClient.setQueriesData<CachedOutfitList>({ queryKey: queryKeys.outfits.all }, (old) =>
          mapCachedOutfitPages(old, (page) => ({
            ...page,
            outfits: page.outfits.filter((outfit) => !deletedSet.has(outfit.id)),
            total: page.total - deletedSet.size,
          })),
        );
      }

      return { previousData };
    },
    onError: (_err, _params, context) => {
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      invalidateOutfitCaches(queryClient);
    },
  });
}

export function useCalendarOutfits(year: number, month: number, filters: OutfitFilters = {}) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  const date_from = formatDateKey(new Date(year, month - 1, 1));
  const date_to = formatDateKey(new Date(year, month, 0));

  const params: Record<string, string> = {
    page: '1',
    page_size: String(MAX_PAGE_SIZE),
    date_from,
    date_to,
  };

  if (filters.status) params.status = filters.status;
  if (filters.occasion) params.occasion = filters.occasion;

  return useQuery({
    queryKey: queryKeys.calendarOutfits.month(year, month, filters),
    queryFn: () => api.get<OutfitListResponse>('/outfits', { params }),
    enabled: status !== 'loading',
  });
}

export function usePendingOutfits(limit = 3) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  const params: Record<string, string> = {
    page: '1',
    page_size: String(limit),
    status: 'pending',
  };

  return useQuery({
    queryKey: queryKeys.pendingOutfits.list(limit),
    queryFn: () => api.get<OutfitListResponse>('/outfits', { params }),
    enabled: status !== 'loading',
  });
}

// --- Family rating hooks ---

export function useSubmitFamilyRating() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ outfitId, rating, comment }: { outfitId: string; rating: number; comment?: string }) =>
      api.post<FamilyRating>(`/outfits/${outfitId}/family-rating`, { rating, comment }),
    onSuccess: (_, { outfitId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.outfits.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.outfit(outfitId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.familyRatings(outfitId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarOutfits.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.familyOutfits.all });
    },
  });
}

export function useFamilyRatings(outfitId: string | undefined) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.familyRatings(outfitId),
    queryFn: () => api.get<FamilyRating[]>(`/outfits/${outfitId}/family-ratings`),
    enabled: !!outfitId && status !== 'loading',
  });
}

export function useDeleteFamilyRating() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (outfitId: string) => api.delete<void>(`/outfits/${outfitId}/family-rating`),
    onSuccess: (_, outfitId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.outfits.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.outfit(outfitId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.familyRatings(outfitId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.familyOutfits.all });
    },
  });
}

export function useFamilyOutfits(
  memberId: string | undefined,
  page = 1,
  pageSize = DEFAULT_PAGE_SIZE
) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  const params: Record<string, string> = {
    page: String(page),
    page_size: String(pageSize),
    family_member_id: memberId || '',
  };

  return useQuery({
    queryKey: queryKeys.familyOutfits.list(memberId, page, pageSize),
    queryFn: () => api.get<OutfitListResponse>('/outfits', { params }),
    enabled: !!memberId && status !== 'loading',
  });
}
