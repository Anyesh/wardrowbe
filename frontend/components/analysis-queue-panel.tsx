'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import { AlertCircle, CheckCircle2, Loader2, RotateCw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  deriveQueueSummary,
  formatAnalyzingElapsed,
  formatDurationSeconds,
} from '@/lib/hooks/use-items';
import { CLOTHING_TYPES, TaggingProgress } from '@/lib/types';
import { cn } from '@/lib/utils';

const CONCURRENCY_DOC_URL = 'https://github.com/Anyesh/wardrowbe/blob/main/.env.example';

type ClothingTypeValue = (typeof CLOTHING_TYPES)[number]['value'];

const KNOWN_TYPES = new Set<string>(CLOTHING_TYPES.map((ct) => ct.value));

const isKnownType = (value: string): value is ClothingTypeValue => KNOWN_TYPES.has(value);

interface AnalysisQueuePanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  progress?: TaggingProgress;
  onRetry: (itemId: string) => void;
  retryPending?: boolean;
}

export function AnalysisQueuePanel({
  open,
  onOpenChange,
  progress,
  onRetry,
  retryPending,
}: AnalysisQueuePanelProps) {
  const t = useTranslations('wardrobe.ai.queue');
  const tc = useTranslations('common');
  const tt = useTranslations('constants.types');
  const [now, setNow] = useState(() => Date.now());

  const current = useMemo(() => progress?.current ?? [], [progress]);
  const recent = progress?.recent ?? [];
  const failures = progress?.failures ?? [];
  const summary = deriveQueueSummary(progress);

  useEffect(() => {
    if (!open || current.length === 0) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [open, current.length]);

  // A freshly uploaded item has neither a name nor a real type until analysis
  // finishes, and `unknown` has no entry in constants.types, so translating it
  // blindly would render a raw key path.
  const describe = (name?: string | null, type?: string) => {
    if (name) return name;
    if (type && isKnownType(type)) return tt(type);
    return t('unnamedItem');
  };

  const averageLabel = formatDurationSeconds(progress?.avg_duration_seconds);
  const etaLabel = formatDurationSeconds(progress?.eta_seconds);
  const isIdle = summary.batchTotal === 0 && recent.length === 0 && failures.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {isIdle ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('idle')}</p>
        ) : (
          <ScrollArea className="max-h-[60vh] pr-3">
            <div className="space-y-5">
              {summary.batchTotal > 0 && (
                <div className="space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">
                      {t('batchProgress', {
                        done: summary.batchDone,
                        total: summary.batchTotal,
                      })}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {t('percentDone', { percent: summary.percentComplete })}
                    </span>
                  </div>
                  <Progress value={summary.percentComplete} className="h-2" />
                  {summary.batchFailed > 0 && (
                    <p className="text-xs text-destructive">
                      {t('batchFailed', { count: summary.batchFailed })}
                    </p>
                  )}
                </div>
              )}

              {current.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('nowAnalyzing')}
                  </h3>
                  {current.map((entry) => (
                    <div key={entry.item_id} className="flex items-center gap-3">
                      <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded bg-muted">
                        {entry.image_url && (
                          <Image
                            src={entry.image_url}
                            alt={describe(entry.name, entry.type)}
                            fill
                            sizes="40px"
                            className="object-cover"
                          />
                        )}
                      </div>
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {describe(entry.name, entry.type)}
                      </span>
                      <Badge variant="secondary" className="gap-1 text-xs">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {formatAnalyzingElapsed(entry.started_at, now)}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}

              {current.length === 0 && summary.remaining > 0 && (
                <p className="text-sm text-muted-foreground">{t('waitingToStart')}</p>
              )}

              {(averageLabel || summary.batchTotal > 0) && (
                <div
                  className={cn(
                    'grid gap-3 rounded-md border p-3 text-sm',
                    summary.remaining > 0 ? 'grid-cols-2' : 'grid-cols-1'
                  )}
                >
                  <div>
                    <p className="text-xs text-muted-foreground">{t('averageLabel')}</p>
                    <p className="font-medium">{averageLabel ?? t('noEstimateYet')}</p>
                  </div>
                  {summary.remaining > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground">{t('remainingLabel')}</p>
                      <p className="font-medium">{etaLabel ?? t('noEstimateYet')}</p>
                    </div>
                  )}
                </div>
              )}

              {recent.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('recentlyFinished')}
                  </h3>
                  {recent.map((entry) => (
                    <div key={entry.item_id} className="flex items-center gap-2 text-sm">
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      <span className="min-w-0 flex-1 truncate">
                        {describe(entry.name, entry.type)}
                      </span>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {formatDurationSeconds(entry.duration_seconds) ?? t('durationUnknown')}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {failures.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('failedHeading')}
                  </h3>
                  {failures.map((entry) => (
                    <div
                      key={entry.item_id}
                      className="flex items-start gap-2 rounded-md border border-destructive/30 p-2 text-sm"
                    >
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{describe(entry.name, entry.type)}</p>
                        <p className="break-words text-xs text-muted-foreground">
                          {entry.error || t('unknownError')}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 shrink-0 px-2 text-xs"
                        disabled={retryPending}
                        onClick={() => onRetry(entry.item_id)}
                      >
                        <RotateCw className="mr-1 h-3 w-3" />
                        {tc('retry')}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </ScrollArea>
        )}

        <p className="text-xs text-muted-foreground">
          {t('concurrency', { count: progress?.concurrency ?? 1 })}{' '}
          <a
            href={CONCURRENCY_DOC_URL}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2"
          >
            {t('concurrencyLink')}
          </a>
        </p>
      </DialogContent>
    </Dialog>
  );
}
