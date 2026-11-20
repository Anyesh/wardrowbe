import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError, NetworkError } from '@/lib/api';
import { DEFAULT_STALE_TIME } from '@/lib/hooks/query-timing';

export type DescribeError = (error: unknown) => string;

function handleError(error: unknown, describe: DescribeError) {
  if (error instanceof NetworkError) {
    toast.error(describe(error));
  } else if (error instanceof ApiError) {
    if (error.status === 401) return;
    if (error.status === 503) {
      toast.error(describe(error), { duration: 8000 });
    } else {
      toast.error(describe(error));
    }
  }
}

// A caller that shows its own translated toast (or handles the failure silently) sets
// meta.toastsOwnErrors, so that a second, generic toast does not appear beside it.
export function createQueryClient(describe: DescribeError): QueryClient {
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
        handleError(error, describe);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.toastsOwnErrors) return;
        handleError(error, describe);
      },
    }),
  });
}
