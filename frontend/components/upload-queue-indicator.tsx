'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslations } from 'next-intl';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useFeatures } from '@/lib/hooks/use-features';
import * as uploadManager from '@/lib/upload-manager';
import { getPendingUploads } from '@/lib/upload-queue';
import type { DrainState, TerminalRecord } from '@/lib/upload-manager';

const BYTES_PER_MB = 1024 * 1024;

type Translator = (key: string, values?: Record<string, string | number>) => string;

function failureMessage(
  t: Translator,
  record: TerminalRecord,
  limitMb: number | undefined
): string {
  const name = record.filename;
  switch (record.errorCode) {
    case 'too_large':
      // A proxy can reject a file below the app's own limit with a 413, and
      // quoting that limit would then contradict the file's actual size.
      return limitMb !== undefined && record.size > limitMb * BYTES_PER_MB
        ? t('failure.tooLarge', { name, limit: limitMb })
        : t('failure.tooLargeForServer', { name });
    case 'unsupported_format':
      return t('failure.unsupportedFormat', { name });
    case 'duplicate':
      return t('failure.duplicate', { name });
    default:
      return t('failure.generic', { name });
  }
}

export function UploadQueueIndicator() {
  const queryClient = useQueryClient();
  const t = useTranslations('wardrobe.uploadQueue');
  const { data: features } = useFeatures();
  const [state, setState] = useState<DrainState | null>(null);
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

  const anyRetryable = state.terminalRecords.some((record) => record.retryable);

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
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
              <span className="text-sm">{t('failedCount', { count: state.terminalRecords.length })}</span>
            </div>

            <ul className="max-h-40 space-y-1 overflow-y-auto">
              {state.terminalRecords.map((record) => (
                <li key={record.id} className="flex items-start justify-between gap-2 text-xs">
                  <span className="min-w-0 break-words">
                    {failureMessage(t, record, features?.max_upload_size_mb)}
                  </span>
                  <div className="flex shrink-0 items-center gap-2">
                    {record.retryable && (
                      <button
                        type="button"
                        className="text-primary hover:underline"
                        onClick={() => uploadManager.retry(record.id)}
                      >
                        {t('retry')}
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-muted-foreground hover:underline"
                      onClick={() => uploadManager.dismiss(record.id)}
                    >
                      {t('dismiss')}
                    </button>
                  </div>
                </li>
              ))}
            </ul>

            <div className="flex items-center gap-2">
              {anyRetryable && (
                <Button size="sm" variant="outline" onClick={() => uploadManager.retryAll()}>
                  {t('retryAll')}
                </Button>
              )}
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
