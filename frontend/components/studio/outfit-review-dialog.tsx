'use client';

import Image from 'next/image';
import { ArrowLeftRight, Check, Loader2, Minus, Plus, RotateCcw, Shirt } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTypeLabel } from '@/lib/hooks/use-translated-constants';
import type { StudioItem } from '@/lib/studio/editor-state';
import {
  canApplySuggestion,
  type OutfitCheckResult,
  type OutfitCheckSuggestion,
} from '@/lib/studio/outfit-check';
import { cn } from '@/lib/utils';

interface OutfitReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  destination: string;
  review: OutfitCheckResult | null;
  items: StudioItem[];
  onApply: (suggestion: OutfitCheckSuggestion) => void;
  onRecheck: () => void;
  isRechecking: boolean;
}

function ratingTone(rating: number): string {
  if (rating >= 8) return 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200';
  if (rating >= 5) return 'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200';
  return 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200';
}

const APPLY_ICON = { replace: ArrowLeftRight, add: Plus, remove: Minus } as const;

export function OutfitReviewDialog({
  open,
  onOpenChange,
  destination,
  review,
  items,
  onApply,
  onRecheck,
  isRechecking,
}: OutfitReviewDialogProps) {
  const t = useTranslations('outfits.review');
  const typeLabel = useTypeLabel();
  if (!review) return null;

  const itemName = (id: string | null) => {
    const item = items.find((i) => i.id === id);
    return item ? item.name || typeLabel(item.type) : null;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col gap-0 p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-4 border-b">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 space-y-1">
              <DialogTitle>{t('title')}</DialogTitle>
              <DialogDescription className="truncate">{destination}</DialogDescription>
            </div>
            <div
              className={cn('shrink-0 rounded-full px-3 py-1 text-sm font-semibold', ratingTone(review.rating))}
              aria-label={t('ratingLabel', { rating: review.rating })}
            >
              {review.rating}/10
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <section className="space-y-2">
            {review.verdict && <Badge variant="secondary">{review.verdict}</Badge>}
            {review.opinion && (
              <p className="text-sm leading-relaxed whitespace-pre-line">{review.opinion}</p>
            )}
          </section>

          {(review.strengths.length > 0 || review.improvements.length > 0) && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {[
                { key: 'strengths', points: review.strengths },
                { key: 'improvements', points: review.improvements },
              ].map(
                ({ key, points }) =>
                  points.length > 0 && (
                    <section key={key} className="rounded-lg border p-4 space-y-2">
                      <h3 className="text-sm font-medium">{t(key)}</h3>
                      <ul className="list-disc pl-4 space-y-1 text-sm text-muted-foreground">
                        {points.map((point, i) => (
                          <li key={i}>{point}</li>
                        ))}
                      </ul>
                    </section>
                  )
              )}
            </div>
          )}

          {review.suggestions.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-sm font-medium">{t('suggestions')}</h3>
              {review.suggestions.map((suggestion, idx) => {
                const replacement = suggestion.replacement_item;
                const actionable = suggestion.action !== 'styling_tip';
                const applicable = canApplySuggestion(items, suggestion);
                const target = itemName(suggestion.target_item_id);
                const Icon = actionable
                  ? APPLY_ICON[suggestion.action as keyof typeof APPLY_ICON]
                  : null;
                return (
                  <article key={idx} className="rounded-lg border p-4 space-y-3">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{t(`actions.${suggestion.action}`)}</Badge>
                        <h4 className="text-sm font-medium">{suggestion.title}</h4>
                      </div>
                      {suggestion.description && (
                        <p className="text-sm text-muted-foreground">{suggestion.description}</p>
                      )}
                      {suggestion.reason && (
                        <p className="text-xs text-muted-foreground italic">{suggestion.reason}</p>
                      )}
                    </div>

                    {actionable && (
                      <div className="flex items-center justify-between gap-3 rounded-md bg-muted/40 p-2">
                        <div className="flex min-w-0 items-center gap-2.5">
                          {replacement && (
                            <div className="h-12 w-12 shrink-0 overflow-hidden rounded-md border bg-background flex items-center justify-center">
                              {replacement.thumbnail_url || replacement.image_url ? (
                                <Image
                                  src={(replacement.thumbnail_url || replacement.image_url)!}
                                  alt={replacement.name || typeLabel(replacement.type)}
                                  width={48}
                                  height={48}
                                  className="h-full w-full object-cover"
                                />
                              ) : (
                                <Shirt className="h-5 w-5 text-muted-foreground" />
                              )}
                            </div>
                          )}
                          <p className="min-w-0 truncate text-xs">
                            {suggestion.action === 'replace' && target && replacement
                              ? `${target} → ${replacement.name || typeLabel(replacement.type)}`
                              : suggestion.action === 'remove'
                                ? target
                                : replacement && (replacement.name || typeLabel(replacement.type))}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant={applicable ? 'default' : 'outline'}
                          disabled={!applicable}
                          onClick={() => onApply(suggestion)}
                          className="shrink-0"
                        >
                          {applicable && Icon ? (
                            <Icon className="mr-1 h-3.5 w-3.5" />
                          ) : (
                            <Check className="mr-1 h-3.5 w-3.5" />
                          )}
                          {applicable ? t(`apply.${suggestion.action}`) : t('applied')}
                        </Button>
                      </div>
                    )}
                  </article>
                );
              })}
            </section>
          )}
        </div>

        <DialogFooter className="p-4 border-t sm:justify-between gap-2">
          <Button variant="outline" onClick={onRecheck} disabled={isRechecking}>
            {isRechecking ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="mr-1.5 h-4 w-4" />
            )}
            {t('recheck')}
          </Button>
          <Button onClick={() => onOpenChange(false)}>{t('done')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
