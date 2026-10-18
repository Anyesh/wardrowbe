'use client';

import { useRef, type ReactNode } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePhotoTypeLabel } from '@/lib/hooks/use-translated-constants';
import type { PhotoType } from '@/lib/types';

export interface GalleryPhoto {
  id: string;
  src: string;
  thumb?: string | null;
  view?: PhotoType | null;
}

const SWIPE_DISTANCE = 40;

// The item's photos as a carousel: arrows, swipe, arrow keys, thumbnails, and a front/back
// switch when both are labelled. The index is owned by the caller so other controls (rotate,
// remove background) know which photo is showing.
export function ItemGallery({
  photos,
  index,
  onIndexChange,
  alt,
  overlay,
}: {
  photos: GalleryPhoto[];
  index: number;
  onIndexChange: (index: number) => void;
  alt: string;
  overlay?: ReactNode;
}) {
  const t = useTranslations('wardrobe.photos');
  const viewLabel = usePhotoTypeLabel();
  const swipeStart = useRef<number | null>(null);
  const count = photos.length;
  const current = photos[Math.min(index, count - 1)] ?? photos[0];
  const go = (next: number) => onIndexChange((next + count) % count);
  const frontIndex = photos.findIndex((photo) => photo.view === 'front');
  const backIndex = photos.findIndex((photo) => photo.view === 'back');

  if (!current) return null;

  return (
    <div className="space-y-2">
      <div
        className="relative aspect-square overflow-hidden rounded-lg bg-muted outline-none focus-visible:ring-2 focus-visible:ring-ring"
        style={{ touchAction: 'pan-y' }}
        tabIndex={count > 1 ? 0 : -1}
        role={count > 1 ? 'group' : undefined}
        aria-roledescription={count > 1 ? 'carousel' : undefined}
        aria-label={count > 1 ? t('counter', { current: index + 1, total: count }) : undefined}
        onKeyDown={(e) => {
          if (count < 2) return;
          if (e.key === 'ArrowLeft') go(index - 1);
          if (e.key === 'ArrowRight') go(index + 1);
        }}
        onPointerDown={(e) => {
          swipeStart.current = e.clientX;
        }}
        onPointerUp={(e) => {
          if (swipeStart.current === null || count < 2) return;
          const distance = e.clientX - swipeStart.current;
          swipeStart.current = null;
          if (Math.abs(distance) >= SWIPE_DISTANCE) go(distance < 0 ? index + 1 : index - 1);
        }}
      >
        <Image
          key={current.id + current.src}
          src={current.src}
          alt={current.view ? `${alt} - ${viewLabel(current.view)}` : alt}
          fill
          draggable={false}
          className="select-none object-contain"
          sizes="(max-width: 640px) 100vw, 50vw"
        />
        {current.view && (
          <span className="absolute left-2 top-2 rounded-full bg-background/85 px-2 py-0.5 text-[11px] font-medium text-primary shadow-sm backdrop-blur-sm">
            {viewLabel(current.view)}
          </span>
        )}
        {count > 1 && (
          <>
            <button
              type="button"
              className="absolute left-1.5 top-1/2 -translate-y-1/2 rounded-full bg-background/80 p-1.5 text-foreground shadow-sm backdrop-blur-sm hover:bg-background"
              aria-label={t('previous')}
              onClick={() => go(index - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full bg-background/80 p-1.5 text-foreground shadow-sm backdrop-blur-sm hover:bg-background"
              aria-label={t('next')}
              onClick={() => go(index + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <span className="absolute bottom-2 right-2 rounded-full bg-background/85 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground shadow-sm">
              {index + 1}/{count}
            </span>
          </>
        )}
        {overlay}
      </div>

      {frontIndex >= 0 && backIndex >= 0 && (
        <div className="flex justify-center" role="group" aria-label={t('frontBack')}>
          <div className="inline-flex rounded-full border bg-muted/50 p-0.5">
            {[
              { key: 'front', at: frontIndex },
              { key: 'back', at: backIndex },
            ].map(({ key, at }) => (
              <button
                key={key}
                type="button"
                aria-pressed={index === at}
                onClick={() => onIndexChange(at)}
                className={cn(
                  'rounded-full px-4 py-1 text-xs font-medium transition-colors',
                  index === at
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {viewLabel(key)}
              </button>
            ))}
          </div>
        </div>
      )}

      {count > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {photos.map((photo, idx) => (
            <button
              key={photo.id}
              type="button"
              onClick={() => onIndexChange(idx)}
              aria-label={photo.view ? viewLabel(photo.view) : t('counter', { current: idx + 1, total: count })}
              aria-current={idx === index}
              className={cn(
                'relative h-14 w-14 flex-shrink-0 overflow-hidden rounded-md border-2 bg-muted transition-colors',
                idx === index ? 'border-primary' : 'border-transparent hover:border-primary/40'
              )}
            >
              <Image src={photo.thumb || photo.src} alt="" fill className="garment-fit" sizes="56px" />
              {photo.view && (
                <span className="absolute inset-x-0 bottom-0 truncate bg-background/85 px-0.5 text-center text-[9px] font-medium text-primary">
                  {viewLabel(photo.view)}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
