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
}

function fetchFeatures(): Promise<Features> {
  return api.get<Features>('/health/features');
}

const featuresQuery = queryOptions({
  queryKey: queryKeys.features,
  queryFn: fetchFeatures,
  staleTime: SLOW_STALE_TIME,
});

export function useFeatures() {
  const { data: session, status } = useSession();
  applySessionToken(session);

  return useQuery({ ...featuresQuery, enabled: status !== 'loading' });
}

// null means "unknown": callers fall back to learning the limit from the
// server's "Maximum N images per bulk upload" 400, so a failed features
// request must not block an upload.
export async function fetchBulkUploadLimit(queryClient: QueryClient): Promise<number | null> {
  try {
    const features = await queryClient.fetchQuery({ ...featuresQuery, retry: false });
    const limit = features.max_bulk_upload_count;
    return limit !== undefined && limit > 0 ? limit : null;
  } catch (error) {
    console.warn('Could not read the bulk upload limit from /health/features', error);
    return null;
  }
}
