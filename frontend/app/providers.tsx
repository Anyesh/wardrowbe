'use client';

import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { SessionProvider } from 'next-auth/react';
import { useState } from 'react';
import { toast, Toaster } from 'sonner';
import { ThemeProvider } from '@/components/theme-provider';
import { AuthProvider } from '@/components/auth-provider';
import { LanguageProvider } from '@/lib/i18n';
import { ApiError, NetworkError } from '@/lib/api';

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

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
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
          onError: handleError,
        }),
      })
  );

  return (
    <SessionProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <LanguageProvider>
              {children}
              <Toaster richColors position="top-center" />
            </LanguageProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </AuthProvider>
    </SessionProvider>
  );
}
