import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError, NetworkError } from '@/lib/api';
import { DEFAULT_STALE_TIME } from '@/lib/hooks/query-timing';

function handleError(error: unknown) {
  if (error instanceof NetworkError) {
    toast.error(error.message);
  } else if (error instanceof ApiError) {
    // Don't show toast for 401 (handled by auth redirect)
    if (error.status === 401) return;
    // Show descriptive message for configuration/service errors
    if (error.status === 503) {
      toast.error(error.message, { duration: 8000 });
    } else {
      toast.error(error.message);
    }
  }
  // Let other errors bubble up to error boundary
}

export function createQueryClient(): QueryClient {
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
      onError: handleError,
    }),
    mutationCache: new MutationCache({
      // A caller that shows its own translated toast opts out, so that the raw server message
      // does not appear as a second toast beside it.
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.toastsOwnErrors) return;
        handleError(error);
      },
    }),
  });
}
