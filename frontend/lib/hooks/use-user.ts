'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { useSetTokenIfAvailable, applySessionToken } from '@/lib/hooks/use-session-token';
import { getTodayDateStringInTimezone, resolveTimezone } from '@/lib/utils';
import { queryKeys } from '@/lib/hooks/query-keys';
import { readLocaleCookie } from '@/lib/i18n/locales';

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

export function useUserProfile() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: queryKeys.userProfile,
    queryFn: () => api.get<UserProfile>('/users/me'),
    enabled: status !== 'loading',
  });
}

// Returns a getter rather than a value so that a page left open past midnight dates the
// action by when it happens, not when the page rendered.
export function useUserTimezone(): string {
  const { data: profile } = useUserProfile();
  return resolveTimezone(profile?.timezone);
}

export function useUserToday(): () => string {
  const timezone = useUserTimezone();
  return useCallback(() => getTodayDateStringInTimezone(timezone), [timezone]);
}

export function useUpdateUserProfile({ toastsOwnErrors = false } = {}) {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    meta: { toastsOwnErrors },
    mutationFn: async (data: UserProfileUpdate) => {
      applySessionToken(session);
      return api.patch<UserProfile>('/users/me', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userProfile });
    },
  });
}

// The UI language comes from the NEXT_LOCALE cookie or Accept-Language, never from the profile,
// so the profile follows the UI: the tagging worker writes AI descriptions in profile.locale.
// One attempt per locale because a failed save must not repeat on every profile refetch; the
// next page load tries again. A tab whose locale no longer matches the cookie was switched away
// from in another tab, so it must not write its stale language back.
export function useSyncProfileLocale(uiLocale: string) {
  const { data: profile } = useUserProfile();
  const { mutate } = useUpdateUserProfile({ toastsOwnErrors: true });
  const attempted = useRef<string | null>(null);

  useEffect(() => {
    if (!profile || profile.locale === uiLocale || attempted.current === uiLocale) return;
    const cookieLocale = readLocaleCookie();
    if (cookieLocale && cookieLocale !== uiLocale) return;
    attempted.current = uiLocale;
    mutate({ locale: uiLocale });
  }, [profile, uiLocale, mutate]);
}
