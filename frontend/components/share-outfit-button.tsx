'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Loader2, Share2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { MissingPhotosError, renderOutfitCollage, shareOrDownload } from '@/lib/outfit-collage';
import { useOccasionLabel } from '@/lib/hooks/use-translated-constants';
import { formatShortDate } from '@/lib/utils';
import type { Outfit } from '@/lib/types';

type ShareableOutfit = Pick<Outfit, 'id' | 'items' | 'occasion' | 'scheduled_for'> & { name?: string | null };

export function ShareOutfitButton({ outfit, className }: { outfit: ShareableOutfit; className?: string }) {
  const t = useTranslations('share');
  const locale = useLocale();
  const occasionLabel = useOccasionLabel();
  const [busy, setBusy] = useState(false);

  const photoUrls = (items: ShareableOutfit['items']) =>
    [...items]
      .sort((a, b) => a.position - b.position)
      .map((item) => item.image_url || item.thumbnail_url)
      .filter((url): url is string => Boolean(url));
  const hasPhotos = photoUrls(outfit.items).length > 0;

  const share = async () => {
    setBusy(true);
    try {
      const title = outfit.name || t('title', { occasion: occasionLabel(outfit.occasion) });
      const text = {
        title,
        subtitle: outfit.scheduled_for ? formatShortDate(outfit.scheduled_for, locale) : undefined,
        footer: t('footer'),
      };
      let blob: Blob;
      try {
        blob = await renderOutfitCollage(photoUrls(outfit.items), text);
      } catch (error) {
        if (!(error instanceof MissingPhotosError)) throw error;
        // Photo links expire: ask for the outfit again for fresh ones, and try once more.
        const fresh = await api.get<Outfit>(`/outfits/${outfit.id}`);
        blob = await renderOutfitCollage(photoUrls(fresh.items), text);
      }
      const result = await shareOrDownload(blob, `outfit-${outfit.id.slice(0, 8)}.png`, title);
      if (result === 'downloaded') toast.success(t('downloaded'));
    } catch (error) {
      toast.error(error instanceof MissingPhotosError ? t('missingPhotos') : t('error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      onClick={share}
      disabled={busy || !hasPhotos}
      className={className}
    >
      {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Share2 className="mr-2 h-4 w-4" />}
      {t('button')}
    </Button>
  );
}
