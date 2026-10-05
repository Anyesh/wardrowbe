'use client';

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';
import { getTodayDateStringInTimezone } from '@/lib/utils';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  timezone: string;
  locale: string;
  location_lat?: number;
  location_lon?: number;
  location_name?: string;
  family_id?: string;
  role: string;
  onboarding_completed: boolean;
  body_measurements?: Record<string, number | string> | null;
}

export interface UserProfileUpdate {
  display_name?: string;
  timezone?: string;
  locale?: string;
  location_lat?: number;
  location_lon?: number;
  location_name?: string;
  body_measurements?: Record<string, number | string> | null;
}

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useUserProfile() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['user-profile'],
    queryFn: () => api.get<UserProfile>('/users/me'),
    enabled: status !== 'loading',
  });
}

// Returns a getter rather than a value so that a page left open past midnight dates the
// action by when it happens, not when the page rendered.
export function useUserToday(): () => string {
  const { data: profile } = useUserProfile();
  const timezone = profile?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  return useCallback(() => getTodayDateStringInTimezone(timezone), [timezone]);
}

export function useUpdateUserProfile() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (data: UserProfileUpdate) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.patch<UserProfile>('/users/me', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    },
  });
}
