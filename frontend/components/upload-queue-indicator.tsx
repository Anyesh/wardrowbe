'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslations } from 'next-intl';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import * as uploadManager from '@/lib/upload-manager';
import { getPendingUploads } from '@/lib/upload-queue';
import type { DrainState } from '@/lib/upload-manager';

export function UploadQueueIndicator() {
  const queryClient = useQueryClient();
  const t = useTranslations('wardrobe.uploadQueue');
  const [state, setState] = useState<DrainState | null>(null);
  const [expanded, setExpanded] = useState(false);
  // True only for records that already existed before this component
  // mounted (a real resume, e.g. the tab was closed mid-import) - lets the
  // copy say "resuming an earlier import" instead of implying this is a
  // brand new upload, which is what the reporter's own scenario needed to
  // not look stalled on return.
  const resumedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    uploadManager.init(queryClient);
    getPendingUploads().then((records) => {
      if (cancelled) return;
      resumedRef.current = records.length > 0;
      void uploadManager.startDrain();
    });

    const unsubscribe = uploadManager.subscribe(setState);
    uploadManager.getState().then((s) => {
      if (!cancelled) setState(s);
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [queryClient]);

  if (!state || (state.remaining === 0 && state.terminalRecords.length === 0)) {
    return null;
  }

  return (
    <div className="fixed bottom-20 right-4 lg:bottom-4 z-50 w-full max-w-xs">
      <div className="rounded-lg border bg-card p-3 shadow-lg space-y-2">
        {state.remaining > 0 && (
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
            <span className="text-sm">
              {resumedRef.current
                ? t('resuming', { count: state.remaining })
                : t('remaining', { count: state.remaining })}
            </span>
          </div>
        )}
        {state.remaining > 0 && (
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">{t('keepTabOpen')}</p>
            <Button size="sm" variant="ghost" onClick={() => uploadManager.cancelAll()}>
              {t('cancel')}
            </Button>
          </div>
        )}
        {state.storagePersisted === false && (
          <p className="text-xs text-yellow-600">{t('storageNotPersisted')}</p>
        )}

        {state.terminalRecords.length > 0 && (
          <div className="space-y-2 border-t pt-2">
            <button
              type="button"
              className="flex items-center gap-2 text-left"
              onClick={() => setExpanded((e) => !e)}
            >
              <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
              <span className="text-sm">{t('failedCount', { count: state.terminalRecords.length })}</span>
            </button>

            {expanded && (
              <div className="max-h-40 space-y-1 overflow-y-auto">
                {state.terminalRecords.map((record) => (
                  <div key={record.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate" title={record.lastError ?? undefined}>
                      {record.filename}
                    </span>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        className="text-primary hover:underline"
                        onClick={() => uploadManager.retry(record.id)}
                      >
                        {t('retry')}
                      </button>
                      <button
                        type="button"
                        className="text-muted-foreground hover:underline"
                        onClick={() => uploadManager.dismiss(record.id)}
                      >
                        {t('dismiss')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => uploadManager.retryAll()}>
                {t('retryAll')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => uploadManager.dismissAll()}>
                {t('dismissAll')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
