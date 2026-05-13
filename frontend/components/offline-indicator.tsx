'use client';

import { useState, useEffect } from 'react';
import { WifiOff } from 'lucide-react';
import { useTranslations } from 'next-intl';

export function OfflineIndicator() {
  const [isOffline, setIsOffline] = useState(false);
  const t = useTranslations('shared.offlineIndicator');

  useEffect(() => {
    // Check initial state
    setIsOffline(!navigator.onLine);

    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 lg:bottom-4 z-50">
      <div className="flex items-center gap-2 bg-destructive text-destructive-foreground px-4 py-2 rounded-full shadow-lg">
        <WifiOff className="w-4 h-4" />
        <span className="text-sm font-medium">{t('message')}</span>
      </div>
    </div>
  );
}
