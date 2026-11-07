'use client';

import { useLocale } from 'next-intl';
import { useSession } from 'next-auth/react';
import { useSyncProfileLocale } from '@/lib/hooks/use-user';

function SyncLocale() {
  useSyncProfileLocale(useLocale());
  return null;
}

// Gated on the backend token, not the NextAuth status, because a session whose backend sync
// failed is still "authenticated" and has no profile to read.
export function ProfileLocaleSync() {
  const { data: session } = useSession();
  return session?.accessToken ? <SyncLocale /> : null;
}
