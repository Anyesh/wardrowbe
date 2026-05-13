'use client';

import { useState } from 'react';
import { AlertTriangle, Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { OccasionChips } from '@/components/shared/occasion-chips';
import { api, getErrorMessage } from '@/lib/api';
import { ITEM_ROLE } from '@/lib/studio/canonical-order';
import { mergeAiAssist } from '@/lib/studio/ai-assist-merge';
import type { StudioItem } from '@/lib/studio/editor-state';
import type { Outfit, OutfitItem } from '@/lib/hooks/use-outfits';
import { useTranslations } from 'next-intl';

interface DetailsPanelProps {
  items: StudioItem[];
  name: string;
  occasion: string | null;
  onNameChange: (name: string) => void;
  onOccasionChange: (occasion: string) => void;
  onAiMerge: (merged: StudioItem[]) => void;
}

function computeWarnings(items: StudioItem[], t: (key: string) => string): string[] {
  const warnings: string[] = [];
  const roles = items.map((i) => ITEM_ROLE[i.type] ?? '');

  const hasFullBody = roles.includes('full_body');
  const hasTop = roles.includes('base_top');
  const hasBottom = roles.includes('bottom');
  const hasFootwear = roles.includes('footwear');

  if (!hasFullBody) {
    if (hasTop && !hasBottom) {
      warnings.push(t('warnings.noBottoms'));
    }
    if (hasBottom && !hasTop) {
      warnings.push(t('warnings.noTop'));
    }
  }

  const bottomCount = roles.filter((r) => r === 'bottom').length;
  if (bottomCount > 1) {
    warnings.push(t('warnings.multipleBottoms'));
  }

  if (items.length >= 3 && !hasFootwear) {
    warnings.push(t('warnings.noFootwear'));
  }

  return warnings;
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
  const t = useTranslations('studio.details');
  const [aiLoading, setAiLoading] = useState(false);
  const warnings = computeWarnings(items, t);

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
        for (const { item, reason } of skipped) {
          toast.info(
            t('skippedItem', { name: item.name || item.type, reason })
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
      toast.error(getErrorMessage(error, t('aiFailed')));
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
          <span className="text-destructive" aria-label="required">*</span>
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
    </div>
  );
}
