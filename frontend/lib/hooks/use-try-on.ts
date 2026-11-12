'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, API_BASE_PATH, getAccessToken, ApiError } from '@/lib/api';
import { applySessionToken } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import { useTryOnEnabled } from '@/lib/hooks/use-features';

export interface TryOnPhoto {
  image_url: string;
  medium_url: string | null;
  created_at: string;
  updated_at: string;
}

export type TryOnStatus = 'pending' | 'ready' | 'failed';

export interface TryOn {
  status: TryOnStatus;
  image_url: string | null;
  medium_url: string | null;
  error_code: string | null;
  created_at: string;
  stale: boolean;
}

const POLL_INTERVAL_MS = 2000;
// The server treats a pending try-on older than 15 minutes as lost; the page stops waiting sooner.
const POLL_LIMIT_MS = 4 * 60 * 1000;

export function tryOnErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const detail = (error.data as { detail?: { error_code?: unknown } } | undefined)?.detail;
  return typeof detail?.error_code === 'string' ? detail.error_code : null;
}

async function nullWhenMissing<T>(request: Promise<T>, code: string): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && tryOnErrorCode(error) === code) {
      return null;
    }
    throw error;
  }
}

export function pollInterval(data: TryOn | null | undefined, now = Date.now()): number | false {
  if (data?.status !== 'pending') return false;
  return now - new Date(data.created_at).getTime() < POLL_LIMIT_MS ? POLL_INTERVAL_MS : false;
}

export function useTryOnPhoto() {
  const { data: session, status } = useSession();
  const enabled = useTryOnEnabled();
  applySessionToken(session);

  return useQuery({
    queryKey: queryKeys.tryOnPhoto,
    queryFn: () => nullWhenMissing(api.get<TryOnPhoto>('/users/me/try-on-photo'), 'TRY_ON_NO_PHOTO'),
    enabled: enabled && status !== 'loading',
    meta: { toastsOwnErrors: true },
  });
}

export function useUploadTryOnPhoto() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (file: File) => {
      const token = session?.accessToken || getAccessToken();
      const formData = new FormData();
      formData.append('image', file);

      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_PATH}/users/me/try-on-photo`, {
        method: 'PUT',
        body: formData,
        credentials: 'include',
        headers,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(
          typeof data.detail === 'string' ? data.detail : 'Failed to upload photo',
          response.status,
          data
        );
      }

      return response.json() as Promise<TryOnPhoto>;
    },
    meta: { toastsOwnErrors: true },
    onSuccess: (photo) => {
      queryClient.setQueryData(queryKeys.tryOnPhoto, photo);
      // A new photo deletes every try-on drawn from the old one.
      queryClient.removeQueries({ queryKey: queryKeys.tryOnAll });
    },
  });
}

export function useDeleteTryOnPhoto() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async () => {
      applySessionToken(session);
      return api.delete('/users/me/try-on-photo');
    },
    meta: { toastsOwnErrors: true },
    onSuccess: () => {
      queryClient.setQueryData(queryKeys.tryOnPhoto, null);
      queryClient.removeQueries({ queryKey: queryKeys.tryOnAll });
    },
  });
}

export function useOutfitTryOn(outfitId: string | undefined) {
  const { data: session, status } = useSession();
  const enabled = useTryOnEnabled();
  applySessionToken(session);

  return useQuery({
    queryKey: queryKeys.tryOn(outfitId ?? ''),
    queryFn: () =>
      nullWhenMissing(api.get<TryOn>(`/outfits/${outfitId}/try-on`), 'TRY_ON_NONE'),
    enabled: enabled && !!outfitId && status !== 'loading',
    refetchInterval: (query) => pollInterval(query.state.data),
    meta: { toastsOwnErrors: true },
  });
}

export function useGenerateTryOn() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async ({ outfitId, regenerate }: { outfitId: string; regenerate?: boolean }) => {
      applySessionToken(session);
      return api.post<TryOn>(`/outfits/${outfitId}/try-on${regenerate ? '?regenerate=true' : ''}`);
    },
    meta: { toastsOwnErrors: true },
    onSuccess: (data, { outfitId }) => {
      queryClient.setQueryData(queryKeys.tryOn(outfitId), data);
    },
    onError: (error, { outfitId }) => {
      // Someone else (another tab) may already be drawing it; pick that up.
      if (tryOnErrorCode(error) === 'TRY_ON_IN_PROGRESS') {
        queryClient.invalidateQueries({ queryKey: queryKeys.tryOn(outfitId) });
      }
    },
  });
}

export function useDeleteTryOn() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (outfitId: string) => {
      applySessionToken(session);
      return api.delete(`/outfits/${outfitId}/try-on`);
    },
    meta: { toastsOwnErrors: true },
    onSuccess: (_, outfitId) => {
      queryClient.setQueryData(queryKeys.tryOn(outfitId), null);
    },
  });
}
