'use client';

import { useEffect } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
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
              页面加载失败
            </h2>
            <p className="text-muted-foreground mb-6 max-w-sm">
              加载内容时发生错误，这可能是一个
              临时问题。
            </p>
            <Button onClick={reset}>
              <RefreshCw className="w-4 h-4 mr-2" />
              重试
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
