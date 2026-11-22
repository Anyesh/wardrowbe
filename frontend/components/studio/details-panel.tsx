'use client';

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, MessageSquareText, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { OccasionChips } from '@/components/shared/occasion-chips';
import { OutfitReviewDialog } from '@/components/studio/outfit-review-dialog';
import { api } from '@/lib/api';
import { useDescribeError } from '@/lib/errors';
import { mergeAiAssist } from '@/lib/studio/ai-assist-merge';
import {
  applySuggestion,
  type OutfitCheckPayload,
  type OutfitCheckResult,
  type OutfitCheckSuggestion,
} from '@/lib/studio/outfit-check';
import { computeWarnings } from '@/lib/studio/warnings';
import type { StudioItem } from '@/lib/studio/editor-state';
import type { Outfit, OutfitItem } from '@/lib/hooks/use-outfits';
import { useTranslations } from 'next-intl';
import { useTypeLabel } from '@/lib/hooks/use-translated-constants';
import { useAiUiEnabled } from '@/lib/hooks/use-features';

interface DetailsPanelProps {
  items: StudioItem[];
  name: string;
  occasion: string | null;
  onNameChange: (name: string) => void;
  onOccasionChange: (occasion: string) => void;
  onAiMerge: (merged: StudioItem[]) => void;
}

function toStudioItem(item: OutfitItem): StudioItem {
  return {
    id: item.id,
    type: item.type,
    name: item.name,
    thumbnail_url: item.thumbnail_url ?? null,
    image_url: item.image_url ?? null,
    primary_color: item.primary_color,
  };
}

export function DetailsPanel({
  items,
  name,
  occasion,
  onNameChange,
  onOccasionChange,
  onAiMerge,
}: DetailsPanelProps) {
  const typeLabel = useTypeLabel();
  const itemLabel = (item: StudioItem) => item.name || typeLabel(item.type);
  const t = useTranslations('outfits.details');
  const describeError = useDescribeError();
  const [aiLoading, setAiLoading] = useState(false);
  const aiUiEnabled = useAiUiEnabled();
  const warnings = computeWarnings(items, t);
  const [checking, setChecking] = useState(false);
  const [destination, setDestination] = useState('');
  const [review, setReview] = useState<OutfitCheckResult | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const canCheck = items.length > 0 && !!occasion && destination.trim().length >= 2;
  // What the outfit, occasion and destination are now, so an answer that comes back after the
  // user changed any of them is dropped rather than shown against a different outfit.
  const contextKey = JSON.stringify([items.map((i) => i.id), occasion, destination.trim()]);
  const latestContext = useRef(contextKey);
  useEffect(() => {
    latestContext.current = contextKey;
  }, [contextKey]);

  const handleCheck = async () => {
    if (!canCheck || !occasion) return;
    setChecking(true);
    const requested = contextKey;
    try {
      const payload: OutfitCheckPayload = {
        items: items.map((i) => i.id),
        destination: destination.trim(),
        occasion,
      };
      const result = await api.post<OutfitCheckResult>('/outfits/check', payload);
      if (latestContext.current !== requested) {
        toast.info(t('checkOutdated'));
        return;
      }
      setReview(result);
      setReviewOpen(true);
    } catch (error) {
      toast.error(describeError(error, t('checkFailed')));
    } finally {
      setChecking(false);
    }
  };

  const handleApply = (suggestion: OutfitCheckSuggestion) => {
    onAiMerge(applySuggestion(items, suggestion));
  };

  const handleAiAssist = async () => {
    if (items.length === 0 || !occasion) {
      toast.error(t('aiAssistError'));
      return;
    }
    setAiLoading(true);
    try {
      const result = await api.post<Outfit>('/outfits/suggest', {
        occasion,
        include_items: items.map((i) => i.id),
      });

      const aiStudioItems = result.items.map(toStudioItem);
      const { merged, skipped } = mergeAiAssist(items, aiStudioItems);

      onAiMerge(merged);

      if (skipped.length > 0) {
        for (const { item, conflict } of skipped) {
          toast.info(
            t('skippedItem', { name: itemLabel(item), other: itemLabel(conflict) })
          );
        }
      } else if (merged.length > items.length) {
        toast.success(
          t('addedItems', { count: merged.length - items.length })
        );
      } else {
        toast.info(t('aiNoSuggestions'));
      }
    } catch (error) {
      toast.error(describeError(error, t('aiFailed')));
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="studio-name" className="flex items-center gap-1">
          {t('name')}
          <span className="text-xs text-muted-foreground font-normal ml-1">
            {t('nameRequired')}
          </span>
        </Label>
        <Input
          id="studio-name"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder={t('namePlaceholder')}
          maxLength={100}
        />
      </div>

      <div className="space-y-2">
        <Label className="flex items-center gap-1">
          {t('occasion')}
          <span className="text-destructive" aria-label={t('required')}>*</span>
        </Label>
        <OccasionChips selected={occasion} onSelect={onOccasionChange} />
        {!occasion && (
          <p className="text-xs text-muted-foreground mt-1">
            {t('pickOccasion')}
          </p>
        )}
      </div>

      {warnings.length > 0 && (
        <Alert className="border-amber-200 bg-amber-50 text-amber-900">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertDescription>
            <ul className="list-disc pl-4 space-y-1">
              {warnings.map((w) => (
                <li key={w} className="text-xs">
                  {w}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {aiUiEnabled && (
        <Button
          type="button"
          variant="outline"
          className="w-full"
          disabled={items.length === 0 || !occasion || aiLoading}
          onClick={handleAiAssist}
        >
          {aiLoading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              {t('aiThinking')}
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4 mr-2" />
              {t('letAiFinish')}
            </>
          )}
        </Button>
      )}

      {aiUiEnabled && (
        <div className="space-y-2 rounded-lg border p-3">
          <Label htmlFor="studio-destination">{t('destination')}</Label>
          <Input
            id="studio-destination"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder={t('destinationPlaceholder')}
            maxLength={200}
          />
          <p className="text-xs text-muted-foreground">{t('destinationHelp')}</p>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={!canCheck || checking}
            onClick={handleCheck}
          >
            {checking ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {t('checking')}
              </>
            ) : (
              <>
                <MessageSquareText className="h-4 w-4 mr-2" />
                {t('checkOutfit')}
              </>
            )}
          </Button>
        </div>
      )}

      <OutfitReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        destination={destination.trim()}
        review={review}
        items={items}
        onApply={handleApply}
        onRecheck={handleCheck}
        isRechecking={checking}
      />
    </div>
  );
}
