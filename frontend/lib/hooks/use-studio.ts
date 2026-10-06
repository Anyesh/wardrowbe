import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';

import { api } from '@/lib/api';
import { useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import type { Outfit } from '@/lib/hooks/use-outfits';
import { queryKeys } from '@/lib/hooks/query-keys';
import { invalidateEveryItemWearCache } from '@/lib/hooks/cache-invalidation';

export interface StudioCreatePayload {
  items: string[];
  occasion: string;
  name?: string;
  scheduled_for?: string | null;
  mark_worn?: boolean;
  source_item_id?: string | null;
}

export function useCreateStudioOutfit() {
  const qc = useQueryClient();
  useSetTokenIfAvailable();
  return useMutation({
    mutationFn: (payload: StudioCreatePayload) =>
      api.post<Outfit>('/outfits/studio', payload),
    onSuccess: (_, payload) => {
      qc.invalidateQueries({ queryKey: queryKeys.outfits.all });
      qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
      qc.invalidateQueries({ queryKey: queryKeys.learning.all });
      if (payload.mark_worn) invalidateEveryItemWearCache(qc);
    },
  });
}

export interface WoreInsteadPayload {
  items: string[];
  rating?: number;
  comment?: string;
  scheduled_for?: string | null;
}

export function useCreateWoreInstead(originalOutfitId: string) {
  const qc = useQueryClient();
  useSetTokenIfAvailable();
  return useMutation({
    mutationFn: (payload: WoreInsteadPayload) =>
      api.post<Outfit>(`/outfits/${originalOutfitId}/wore-instead`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.outfits.all });
      qc.invalidateQueries({ queryKey: queryKeys.outfit(originalOutfitId) });
      qc.invalidateQueries({ queryKey: queryKeys.pendingOutfits.all });
      qc.invalidateQueries({ queryKey: queryKeys.calendarOutfits.all });
      qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
      qc.invalidateQueries({ queryKey: queryKeys.learning.all });
      invalidateEveryItemWearCache(qc);
    },
  });
}

export function useCloneToLookbook(sourceOutfitId: string) {
  const qc = useQueryClient();
  useSetTokenIfAvailable();
  return useMutation({
    mutationFn: (payload: { name: string }) =>
      api.post<Outfit>(`/outfits/${sourceOutfitId}/clone-to-lookbook`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.outfits.all });
    },
  });
}

export function useWearToday(templateId: string) {
  const qc = useQueryClient();
  useSetTokenIfAvailable();
  return useMutation({
    mutationFn: (payload: { scheduled_for?: string | null }) =>
      api.post<Outfit>(`/outfits/${templateId}/wear-today`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.outfits.all });
      qc.invalidateQueries({ queryKey: queryKeys.calendarOutfits.all });
      invalidateEveryItemWearCache(qc);
    },
  });
}

export interface PatchOutfitPayload {
  name?: string;
  items?: string[];
}

export function usePatchOutfit() {
  const qc = useQueryClient();
  useSetTokenIfAvailable();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PatchOutfitPayload }) =>
      api.patch<Outfit>(`/outfits/${id}`, payload),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.outfit(id) });
      qc.invalidateQueries({ queryKey: queryKeys.outfits.all });
    },
  });
}
