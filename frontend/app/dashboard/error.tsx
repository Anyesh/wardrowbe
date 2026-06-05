'use client';

import { useEffect } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useI18n } from '@/lib/i18n';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useI18n();

  useEffect(() => {
    console.error('Dashboard error:', error);
  }, [error]);

  return (
    <div className="space-y-6">
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex flex-col items-center text-center py-8">
            <div className="rounded-full bg-destructive/10 p-4 mb-4">
              <AlertTriangle className="w-8 h-8 text-destructive" />
            </div>
            <h2 className="text-xl font-semibold mb-2">
              {t('error.loadFailed')}
            </h2>
            <p className="text-muted-foreground mb-6 max-w-sm">
              {t('error.loadFailedDesc')}
            </p>
            <Button onClick={reset}>
              <RefreshCw className="w-4 h-4 mr-2" />
              {t('common.retry')}
            </Button>
            {process.env.NODE_ENV === 'development' && (
              <pre className="mt-6 p-4 bg-muted rounded-lg text-left text-xs overflow-auto max-h-48 w-full">
                {error.message}
              </pre>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}