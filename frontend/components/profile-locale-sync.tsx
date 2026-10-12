'use client';

import { useLocale } from 'next-intl';
import { useSession } from 'next-auth/react';
import { useSyncProfileLocale } from '@/lib/hooks/use-user';

function SyncLocale() {
  useSyncProfileLocale(useLocale());
  return null;
}

// Mounted only once signed in, so the login page never requests a profile it cannot read.
export function ProfileLocaleSync() {
  const { status } = useSession();
  return status === 'authenticated' ? <SyncLocale /> : null;
}
