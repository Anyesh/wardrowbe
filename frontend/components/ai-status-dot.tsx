'use client';

import { useTranslations } from 'next-intl';
import { useAIStatus } from '@/lib/hooks/use-ai-status';
import { cn } from '@/lib/utils';

const DOT: Record<string, string> = {
  online: 'bg-green-500',
  model_missing: 'bg-amber-500',
  offline: 'bg-red-500',
  disabled: 'bg-muted-foreground',
  unknown: 'bg-muted-foreground',
};

/** Green when the AI server answers with the configured models, amber when a model is missing,
 * red when the server does not answer. */
export function AIStatusDot({ className }: { className?: string }) {
  const t = useTranslations('nav.aiStatus');
  const { data, isError } = useAIStatus();
  const state = isError ? 'unknown' : (data?.status ?? 'unknown');
  const detail =
    state === 'model_missing' && data?.missing_models.length
      ? t('missingDetail', { models: data.missing_models.join(', ') })
      : data?.vision_model
        ? t('modelDetail', { model: data.vision_model })
        : t('unknownDetail');

  return (
    <div className={cn('flex items-center gap-2 text-xs text-muted-foreground', className)} title={detail}>
      <span className="relative flex h-2.5 w-2.5">
        {state === 'online' && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-60" />
        )}
        <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', DOT[state])} />
      </span>
      <span>{t(state)}</span>
    </div>
  );
}
