'use client';

import { useEffect } from 'react';
import { WifiOff } from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { useOffline } from '@/lib/hooks/use-offline';

export function OfflineIndicator() {
  const { t } = useI18n();
  const isOffline = useOffline();

  useEffect(() => {
    if (isOffline) {
      document.body.classList.add('offline');
    } else {
      document.body.classList.remove('offline');
    }
    return () => document.body.classList.remove('offline');
  }, [isOffline]);

  if (!isOffline) return null;

  return (
    <div className="fixed bottom-16 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-destructive px-4 py-2 text-destructive-foreground text-sm lg:bottom-0">
      <WifiOff className="h-4 w-4" />
      <span>{t('offline.indicator')}</span>
    </div>
  );
}