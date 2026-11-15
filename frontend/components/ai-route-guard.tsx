'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { isAiRoute } from '@/lib/ai-routes';
import { useAiUiEnabled } from '@/lib/hooks/use-features';

export function AiRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const aiUiEnabled = useAiUiEnabled();
  const onAiRoute = isAiRoute(pathname);

  useEffect(() => {
    if (onAiRoute && aiUiEnabled === false) router.replace('/dashboard');
  }, [onAiRoute, aiUiEnabled, router]);

  if (onAiRoute && !aiUiEnabled) return null;
  return <>{children}</>;
}
