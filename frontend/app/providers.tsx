'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import { SessionProvider } from 'next-auth/react';
import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Toaster } from 'sonner';
import { ThemeProvider } from '@/components/theme-provider';
import { AuthProvider } from '@/components/auth-provider';
import { ProfileLocaleSync } from '@/components/profile-locale-sync';
import { createQueryClient } from '@/lib/query-client';
import { useDescribeError } from '@/lib/errors';

export function Providers({ children }: { children: React.ReactNode }) {
  const t = useTranslations('errors');
  const describeError = useDescribeError();
  // The client outlives locale changes, so its toast reads the current translator through a ref.
  const toastText = useRef((error: unknown) => describeError(error, t('default')));
  toastText.current = (error: unknown) => describeError(error, t('default'));
  const [queryClient] = useState(() => createQueryClient((error) => toastText.current(error)));

  return (
    <SessionProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <ProfileLocaleSync />
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            {children}
            <Toaster richColors position="top-center" />
          </ThemeProvider>
        </QueryClientProvider>
      </AuthProvider>
    </SessionProvider>
  );
}
