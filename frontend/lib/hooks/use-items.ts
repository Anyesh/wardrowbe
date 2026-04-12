'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, getAccessToken, setAccessToken, ApiError, NetworkError } from '@/lib/api';
import { Item, ItemListResponse, ItemFilter, WashHistoryEntry, ItemImage } from '@/lib/types';

// Helper to set token if available (for NextAuth mode)
function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useItems(filters: ItemFilter = {}, page = 1, pageSize = 20) {
  const { data: session, status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['items', filters, page, pageSize],
    queryFn: async () => {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      if (filters.type) params.type = filters.type;
      if (filters.colors?.length) params.colors = filters.colors.join(',');
      if (filters.search) params.search = filters.search;
      if (filters.favorite !== undefined) params.favorite = String(filters.favorite);
      if (filters.needs_wash !== undefined) params.needs_wash = String(filters.needs_wash);
      if (filters.is_archived !== undefined) params.is_archived = String(filters.is_archived);
      if (filters.sort_by) params.sort_by = filters.sort_by;
      if (filters.sort_order) params.sort_order = filters.sort_order;
      if (filters.ids) params.ids = filters.ids;

      return api.get<ItemListResponse>('/items', { params });
    },
    enabled: status !== 'loading',
    // Poll more frequently when items are processing (every 5 seconds), otherwise every 30 seconds
    refetchInterval: (query) => {
      const data = query.state.data as ItemListResponse | undefined;
      const hasProcessing = data?.items?.some((item) => item.status === 'processing');
      return hasProcessing ? 5000 : 30000;
    },
  });
}

export function useItem(itemId: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['item', itemId],
    queryFn: () => api.get<Item>(`/items/${itemId}`),
    enabled: !!itemId && status !== 'loading',
  });
}

export function useCreateItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (formData: FormData) => {
      const token = session?.accessToken || getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      let response: Response;
      try {
        // Use the Next.js proxy path for client-side requests
        response = await fetch('/api/v1/items', {
          method: 'POST',
          body: formData,
          credentials: 'include',
          headers,
        });
      } catch {
        if (!navigator.onLine) {
          throw new NetworkError('You appear to be offline. Please check your connection.');
        }
        throw new NetworkError('Unable to connect to server. Please try again.');
      }

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(
          data.detail || 'Failed to create item',
          response.status,
          data
        );
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
    },
  });
}

export function useUpdateItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<Item> }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.patch<Item>(`/items/${id}`, data);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.id] });
    },
  });
}

export function useRemoveBackground() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ id, bg_color }: { id: string; bg_color?: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${id}/remove-background`, { bg_color: bg_color ?? '#FFFFFF' });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['outfits'] });
      queryClient.invalidateQueries({ queryKey: ['calendarOutfits'] });
    },
  });
}

export function useDeleteItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (id: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.delete(`/items/${id}`);
    },
    onMutate: async (deletedId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['items'] });

      // Snapshot previous value
      const previousData = queryClient.getQueriesData({ queryKey: ['items'] });

      // Optimistically remove from all item queries
      queryClient.setQueriesData({ queryKey: ['items'] }, (old: ItemListResponse | undefined) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.filter((item) => item.id !== deletedId),
          total: old.total - 1,
        };
      });

      return { previousData };
    },
    onError: (_err, _id, context) => {
      // Rollback on error
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item-types'] });
    },
  });
}

export function useArchiveItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason?: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${id}/archive`, { reason });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
    },
  });
}

export function useLogWear() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      id,
      worn_at,
      occasion,
    }: {
      id: string;
      worn_at?: string;
      occasion?: string;
    }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${id}/wear`, { worn_at, occasion });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.id] });
    },
  });
}

export function useLogWash() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      id,
      washed_at,
      method,
      notes,
    }: {
      id: string;
      washed_at?: string;
      method?: string;
      notes?: string;
    }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${id}/wash`, { washed_at, method, notes });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['wash-history', variables.id] });
    },
  });
}

export function useWashHistory(itemId: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['wash-history', itemId],
    queryFn: () => api.get<WashHistoryEntry[]>(`/items/${itemId}/wash-history`),
    enabled: !!itemId && status !== 'loading',
  });
}

export interface WearStats {
  total_wears: number;
  days_since_last_worn: number | null;
  average_wears_per_month: number;
  wear_by_month: Record<string, number>;
  wear_by_day_of_week: Record<string, number>;
  most_common_occasion: string | null;
}

export function useItemWearStats(itemId: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['wear-stats', itemId],
    queryFn: () => api.get<WearStats>(`/items/${itemId}/wear-stats`),
    enabled: !!itemId && status !== 'loading',
  });
}

export interface WearHistoryEntry {
  id: string;
  worn_at: string;
  occasion?: string;
  notes?: string;
  outfit?: {
    id: string;
    occasion: string;
    items: Array<{
      id: string;
      type: string;
      name?: string;
      thumbnail_url?: string;
    }>;
  };
}

export function useItemWearHistory(itemId: string, limit = 10) {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['wear-history', itemId],
    queryFn: () => api.get<WearHistoryEntry[]>(`/items/${itemId}/history?limit=${limit}`),
    enabled: !!itemId && status !== 'loading',
  });
}

export function useAddItemImage() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ itemId, file }: { itemId: string; file: File }) => {
      const token = session?.accessToken || getAccessToken();
      const formData = new FormData();
      formData.append('image', file);

      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`/api/v1/items/${itemId}/images`, {
        method: 'POST',
        body: formData,
        credentials: 'include',
        headers,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(data.detail || 'Failed to upload image', response.status, data);
      }

      return response.json() as Promise<ItemImage>;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.itemId] });
    },
  });
}

export function useDeleteItemImage() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ itemId, imageId }: { itemId: string; imageId: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.delete(`/items/${itemId}/images/${imageId}`);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.itemId] });
    },
  });
}

export function useSetPrimaryImage() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ itemId, imageId }: { itemId: string; imageId: string }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${itemId}/images/${imageId}/set-primary`);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.itemId] });
    },
  });
}

export function useRotateImage() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({
      id,
      direction,
    }: {
      id: string;
      direction: 'cw' | 'ccw';
    }) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<Item>(`/items/${id}/rotate?direction=${direction}`);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['outfits'] });
      queryClient.invalidateQueries({ queryKey: ['calendarOutfits'] });
    },
  });
}

export function useItemTypes() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['item-types'],
    queryFn: () => api.get<Array<{ type: string; count: number }>>('/items/types'),
    enabled: status !== 'loading',
  });
}

export function useColorDistribution() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['color-distribution'],
    queryFn: () => api.get<Array<{ color: string; count: number }>>('/items/colors'),
    enabled: status !== 'loading',
  });
}

export function useReanalyzeItem() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (id: string) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<{ job_id: string; status: string }>(`/items/${id}/analyze`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
    },
  });
}

export interface BulkUploadResult {
  filename: string;
  success: boolean;
  item?: Item;
  error?: string;
}

export interface BulkUploadResponse {
  total: number;
  successful: number;
  failed: number;
  results: BulkUploadResult[];
}

export interface BulkDeleteResponse {
  deleted: number;
  failed: number;
  errors: string[];
}

export interface BulkOperationParams {
  // Either provide explicit item_ids, or use select_all with excluded_ids
  item_ids?: string[];
  select_all?: boolean;
  excluded_ids?: string[];
  // Filters to apply when using select_all (to match the current view)
  filters?: {
    type?: string;
    search?: string;
    needs_wash?: boolean;
    favorite?: boolean;
    is_archived?: boolean;
  };
}

export function useBulkDeleteItems() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (params: BulkOperationParams) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<BulkDeleteResponse>('/items/bulk/delete', params);
    },
    onMutate: async (params) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['items'] });

      // Snapshot previous value
      const previousData = queryClient.getQueriesData({ queryKey: ['items'] });

      // Optimistically update UI
      if (params.select_all) {
        // If select_all, remove all items except excluded ones
        const excludedSet = new Set(params.excluded_ids || []);
        queryClient.setQueriesData({ queryKey: ['items'] }, (old: ItemListResponse | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.filter((item) => excludedSet.has(item.id)),
            total: excludedSet.size,
          };
        });
      } else if (params.item_ids) {
        // Remove specific items
        const deletedSet = new Set(params.item_ids);
        queryClient.setQueriesData({ queryKey: ['items'] }, (old: ItemListResponse | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.filter((item) => !deletedSet.has(item.id)),
            total: old.total - params.item_ids!.length,
          };
        });
      }

      return { previousData };
    },
    onError: (_err, _params, context) => {
      // Rollback on error
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ['items'] });
      queryClient.invalidateQueries({ queryKey: ['item-types'] });
    },
  });
}

export interface BulkAnalyzeResponse {
  queued: number;
  failed: number;
  errors: string[];
}

export function useBulkReanalyzeItems() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (params: BulkOperationParams) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.post<BulkAnalyzeResponse>('/items/bulk/analyze', params);
    },
    onMutate: async (params) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['items'] });

      // Snapshot previous value
      const previousData = queryClient.getQueriesData({ queryKey: ['items'] });

      // Optimistically set items to processing status
      if (params.select_all) {
        const excludedSet = new Set(params.excluded_ids || []);
        queryClient.setQueriesData({ queryKey: ['items'] }, (old: ItemListResponse | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              !excludedSet.has(item.id) ? { ...item, status: 'processing' as const } : item
            ),
          };
        });
      } else if (params.item_ids) {
        const itemIdSet = new Set(params.item_ids);
        queryClient.setQueriesData({ queryKey: ['items'] }, (old: ItemListResponse | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              itemIdSet.has(item.id) ? { ...item, status: 'processing' as const } : item
            ),
          };
        });
      }

      return { previousData };
    },
    onError: (_err, _params, context) => {
      // Rollback on error
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ['items'] });
    },
  });
}

export function useBulkCreateItems() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const [uploadProgress, setUploadProgress] = useState(0);

  const mutation = useMutation({
    mutationFn: async (files: File[]) => {
      const token = session?.accessToken || getAccessToken();

      const formData = new FormData();
      files.forEach((file) => {
        formData.append('images', file);
      });

      // Use XMLHttpRequest for upload progress tracking
      return new Promise<BulkUploadResponse>((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(progress);
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText) as BulkUploadResponse;
              resolve(response);
            } catch {
              reject(new ApiError('Invalid response from server', xhr.status, {}));
            }
          } else {
            let errorMessage = 'Failed to upload items';
            try {
              const errorData = JSON.parse(xhr.responseText);
              errorMessage = errorData.detail || errorMessage;
              reject(new ApiError(errorMessage, xhr.status, errorData));
            } catch {
              reject(new ApiError(errorMessage, xhr.status, {}));
            }
          }
        });

        xhr.addEventListener('error', () => {
          if (!navigator.onLine) {
            reject(new NetworkError('You appear to be offline. Please check your connection.'));
          } else {
            reject(new NetworkError('Unable to connect to server. Please try again.'));
          }
        });

        xhr.addEventListener('abort', () => {
          reject(new NetworkError('Upload was cancelled.'));
        });

        xhr.open('POST', '/api/v1/items/bulk');
        xhr.withCredentials = true;
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }
        xhr.send(formData);
      });
    },
    onMutate: () => {
      setUploadProgress(0);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['items'] });
    },
    onSettled: () => {
      // Reset progress when done (success or error)
      setUploadProgress(0);
    },
  });

  return {
    ...mutation,
    uploadProgress,
  };
}
