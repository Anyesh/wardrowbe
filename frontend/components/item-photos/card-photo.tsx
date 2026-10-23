'use client';

import { useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { GalleryHorizontal, Repeat2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Item } from '@/lib/types';

const CARD_SIZES = '(max-width: 640px) 50vw, (max-width: 768px) 33vw, (max-width: 1024px) 25vw, 20vw';

// The other side of the cover: its back when the cover is the front (or unlabelled), its front
// when the cover is the back.
function otherSide(item: Item) {
  const wanted = item.image_view === 'back' ? 'front' : item.image_view === 'front' || !item.image_view ? 'back' : null;
  if (!wanted) return null;
  return (item.additional_images ?? []).find((img) => img.view === wanted) ?? null;
}

// Card image for the wardrobe grid. With both sides photographed, hovering (on devices that can
// hover) or tapping the flip button shows the other side without opening the item.
export function CardPhoto({ item, alt }: { item: Item; alt: string }) {
  const t = useTranslations('wardrobe.photos');
  const [flipped, setFlipped] = useState(false);
  const other = otherSide(item);
  const photoCount = 1 + (item.additional_images?.length ?? 0);

  if (!item.thumbnail_url) return null;

  return (
    <>
      <Image
        src={item.thumbnail_url}
        alt={alt}
        fill
        className={cn(
          'garment-fit transition-opacity duration-300',
          other && (flipped ? 'opacity-0' : '[@media(hover:hover)]:group-hover:opacity-0')
        )}
        sizes={CARD_SIZES}
      />
      {other && (
        <Image
          src={other.thumbnail_url || other.image_url}
          alt=""
          aria-hidden="true"
          fill
          className={cn(
            'garment-fit transition-opacity duration-300',
            flipped ? 'opacity-100' : 'opacity-0 [@media(hover:hover)]:group-hover:opacity-100'
          )}
          sizes={CARD_SIZES}
        />
      )}
      {(photoCount > 1 || other) && (
        <div className="absolute bottom-2 left-2 z-10 flex items-center gap-1">
          {photoCount > 1 && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-background/85 px-1.5 py-0.5 text-[10px] font-medium text-foreground shadow-sm backdrop-blur-sm"
              title={t('countShort', { count: photoCount })}
            >
              <GalleryHorizontal className="h-3 w-3 text-primary" aria-hidden="true" />
              <span aria-label={t('countShort', { count: photoCount })}>{photoCount}</span>
            </span>
          )}
          {other && (
            <button
              type="button"
              className="inline-flex h-6 items-center gap-1 rounded-full bg-background/85 px-1.5 text-[10px] font-medium text-primary shadow-sm backdrop-blur-sm hover:bg-background"
              aria-pressed={flipped}
              aria-label={flipped ? t('showCover') : t(other.view === 'front' ? 'showFront' : 'showBack')}
              onClick={(e) => {
                e.stopPropagation();
                setFlipped((value) => !value);
              }}
            >
              <Repeat2 className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">{t(other.view === 'front' ? 'front' : 'back')}</span>
            </button>
          )}
        </div>
      )}
    </>
  );
}
