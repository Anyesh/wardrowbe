'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Loader2, Share2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { renderOutfitCollage, shareOrDownload } from '@/lib/outfit-collage';
import { useOccasionLabel } from '@/lib/hooks/use-translated-constants';
import { formatShortDate } from '@/lib/utils';
import type { Outfit } from '@/lib/types';

type ShareableOutfit = Pick<Outfit, 'id' | 'items' | 'occasion' | 'scheduled_for'> & { name?: string | null };

export function ShareOutfitButton({ outfit, className }: { outfit: ShareableOutfit; className?: string }) {
  const t = useTranslations('share');
  const locale = useLocale();
  const occasionLabel = useOccasionLabel();
  const [busy, setBusy] = useState(false);

  const share = async () => {
    setBusy(true);
    try {
      const urls = [...outfit.items]
        .sort((a, b) => a.position - b.position)
        .map((item) => item.image_url || item.thumbnail_url)
        .filter((url): url is string => Boolean(url));
      const title = outfit.name || t('title', { occasion: occasionLabel(outfit.occasion) });
      const blob = await renderOutfitCollage(urls, {
        title,
        subtitle: outfit.scheduled_for ? formatShortDate(outfit.scheduled_for, locale) : undefined,
        footer: t('footer'),
      });
      const result = await shareOrDownload(blob, `outfit-${outfit.id.slice(0, 8)}.png`, title);
      if (result === 'downloaded') toast.success(t('downloaded'));
    } catch {
      toast.error(t('error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      onClick={share}
      disabled={busy || outfit.items.length === 0}
      className={className}
    >
      {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Share2 className="mr-2 h-4 w-4" />}
      {t('button')}
    </Button>
  );
}
