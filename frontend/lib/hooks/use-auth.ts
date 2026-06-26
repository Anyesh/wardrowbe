'use client';

import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSession, signOut } from 'next-auth/react';
import { api, setAccessToken, ApiError } from '@/lib/api';
import type { UserProfile } from './use-user';

export function useAuth() {
  const { data: session, status } = useSession();
  const signingOut = useRef(false);

  // Set access token if available from NextAuth
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }

  const hasToken = !!session?.accessToken;
  const syncError = session?.syncError;

  const userQuery = useQuery({
    queryKey: ['auth-user'],
    queryFn: () => api.get<UserProfile>('/users/me'),
    // Only fetch when session is loaded AND we have an access token
    enabled: status === 'authenticated' && hasToken,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (signingOut.current) return;

    if (userQuery.error instanceof ApiError && userQuery.error.status === 401) {
      signingOut.current = true;
      signOut({ redirect: false }).then(() => {
        signingOut.current = false;
      });
      return;
    }

    if (status === 'authenticated' && !hasToken) {
      signingOut.current = true;
      const callbackUrl = syncError
        ? `/login?syncError=${encodeURIComponent(syncError)}`
        : '/login';
      signOut({ callbackUrl }).then(() => {
        signingOut.current = false;
      });
    }
  }, [userQuery.error, status, hasToken, syncError]);

  const isAuthenticated = userQuery.isSuccess && !!userQuery.data;
 
  const isLoading = status === 'loading' || (status === 'authenticated' && userQuery.isPending);

  return {
    user: userQuery.data,
    isAuthenticated,
    isLoading,
    error: userQuery.error,
    // For components that still need session info
    session,
    sessionStatus: status,
  };
}
