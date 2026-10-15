'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, API_BASE_PATH, ApiError, getAccessToken } from '@/lib/api';
import { applySessionToken, useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';

export interface WishlistEntry {
  id: string;
  name: string;
  notes: string | null;
  link: string | null;
  image_url: string | null;
  photo_url: string | null;
  price: string | null;
  item_type: string | null;
  priority: number;
  bought: boolean;
  current_price: string | null;
  price_checked_at: string | null;
  price_dropped_at: string | null;
  created_at: string;
}

export interface WishlistInput {
  name?: string;
  notes?: string | null;
  link?: string | null;
  image_url?: string | null;
  price?: string | null;
  item_type?: string | null;
  priority?: number;
  bought?: boolean;
}

export interface LinkPreview {
  url: string;
  title: string | null;
  image_url: string | null;
  price: string | null;
  currency: string | null;
  site: string | null;
}

export interface WardrobeGap {
  role: string;
  have: number;
  target: number;
}

export function useWishlist() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.wishlist,
    queryFn: () => api.get<WishlistEntry[]>('/wishlist'),
    enabled: status === 'authenticated',
  });
}

export function useWishlistSuggestions() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.wishlistSuggestions,
    queryFn: () => api.get<WardrobeGap[]>('/wishlist/suggestions'),
    enabled: status === 'authenticated',
  });
}

function useWishlistMutation<TVars, TResult>(run: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async (vars: TVars) => {
      applySessionToken(session);
      return run(vars);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.wishlist });
    },
  });
}

export function useAddWishlistEntry() {
  return useWishlistMutation((input: WishlistInput) => api.post<WishlistEntry>('/wishlist', input));
}

export function useUpdateWishlistEntry() {
  return useWishlistMutation(({ id, ...input }: WishlistInput & { id: string }) =>
    api.patch<WishlistEntry>(`/wishlist/${id}`, input)
  );
}

export function useDeleteWishlistEntry() {
  return useWishlistMutation((id: string) => api.delete<void>(`/wishlist/${id}`));
}

async function sendForm<T>(path: string, method: 'PUT', file: File, token?: string | null) {
  const formData = new FormData();
  formData.append('image', file);
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    method,
    body: formData,
    credentials: 'include',
    headers,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof data.detail === 'string' ? data.detail : 'Request failed',
      response.status,
      data
    );
  }
  return response.json() as Promise<T>;
}

export function useUploadWishlistPhoto() {
  const { data: session } = useSession();
  return useWishlistMutation(({ id, file }: { id: string; file: File }) =>
    sendForm<WishlistEntry>(
      `/wishlist/${id}/image`,
      'PUT',
      file,
      session?.accessToken || getAccessToken()
    )
  );
}

export function useLinkPreview() {
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async (url: string) => {
      applySessionToken(session);
      return api.post<LinkPreview>('/wishlist/preview', { url });
    },
  });
}

export function useCheckPrices() {
  return useWishlistMutation(() => api.post<WishlistEntry[]>('/wishlist/check-prices'));
}
