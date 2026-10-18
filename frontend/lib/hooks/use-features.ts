'use client';

import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import { SLOW_STALE_TIME } from '@/lib/hooks/query-timing';

interface Features {
  background_removal: boolean;
  max_upload_size_mb: number;
  max_bulk_upload_count?: number;
  ai_ui_enabled?: boolean;
}

// An upload waits on this request before its first chunk, so a server that never answers
// must not hold the upload.
const UPLOAD_FEATURES_TIMEOUT_MS = 5000;

function fetchFeatures(signal?: AbortSignal): Promise<Features> {
  return api.get<Features>('/health/features', { signal });
}

function withTimeout(signal: AbortSignal, ms: number): AbortSignal {
  const timeout = new AbortController();
  setTimeout(() => timeout.abort(new DOMException('Timed out', 'TimeoutError')), ms);
  if (typeof AbortSignal.any === 'function') return AbortSignal.any([signal, timeout.signal]);
  if (signal.aborted) timeout.abort(signal.reason);
  else signal.addEventListener('abort', () => timeout.abort(signal.reason), { once: true });
  return timeout.signal;
}

const featuresQuery = queryOptions({
  queryKey: queryKeys.features,
  queryFn: () => fetchFeatures(),
  staleTime: SLOW_STALE_TIME,
});

export function useFeatures() {
  const { data: session, status } = useSession();
  applySessionToken(session);

  return useQuery({ ...featuresQuery, enabled: status !== 'loading' });
}

// undefined until the features call answers, so a disabled install never flashes AI UI.
// A failed call or a backend too old to send the flag counts as on, so a default
// install never loses AI UI to a features outage.
export function useAiUiEnabled(): boolean | undefined {
  const { data, isError } = useFeatures();
  if (isError) return true;
  if (!data) return undefined;
  return data.ai_ui_enabled !== false;
}

// null means "unknown": callers fall back to learning the limit from the
// server's "Maximum N images per bulk upload" 400, so a failed features
// request must not block an upload.
export async function fetchBulkUploadLimit(queryClient: QueryClient): Promise<number | null> {
  try {
    const features = await queryClient.fetchQuery({
      ...featuresQuery,
      queryFn: ({ signal }) => fetchFeatures(withTimeout(signal, UPLOAD_FEATURES_TIMEOUT_MS)),
      retry: false,
      // The upload carries on without the limit, so the fetch failure is not the user's problem.
      meta: { toastsOwnErrors: true },
    });
    const limit = features.max_bulk_upload_count;
    return limit !== undefined && limit > 0 ? limit : null;
  } catch (error) {
    console.warn('Could not read the bulk upload limit from /health/features', error);
    return null;
  }
}
