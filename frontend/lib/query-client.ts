import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError, NetworkError } from '@/lib/api';
import { DEFAULT_STALE_TIME } from '@/lib/hooks/query-timing';

function handleError(error: unknown, toastText: (error: unknown) => string) {
  if (error instanceof NetworkError) {
    toast.error(toastText(error));
  } else if (error instanceof ApiError) {
    // Don't show toast for 401 (handled by auth redirect)
    if (error.status === 401) return;
    // Service errors explain a configuration problem, so they stay up long enough to read.
    if (error.status === 503) toast.error(toastText(error), { duration: 8000 });
    else toast.error(toastText(error));
  }
  // Let other errors bubble up to error boundary
}

// A caller that shows its own translated message (or handles the failure silently) sets
// meta.toastsOwnErrors, so that a second, generic toast does not appear beside it.
export function createQueryClient(toastText: (error: unknown) => string): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_TIME,
        retry: (failureCount, error) => {
          // Don't retry on auth errors or client errors
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          // Don't retry network errors (user is likely offline)
          if (error instanceof NetworkError) {
            return false;
          }
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.toastsOwnErrors) return;
        handleError(error, toastText);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.toastsOwnErrors) return;
        handleError(error, toastText);
      },
    }),
  });
}
