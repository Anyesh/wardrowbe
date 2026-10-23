'use client';

import { useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { useTranslations } from 'next-intl';
import { ArrowLeft, ArrowRight, Star, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { nextFreeView } from '@/components/item-photos/photo-manager';
import { usePhotoTypeLabel } from '@/lib/hooks/use-translated-constants';
import { ACCEPTED_IMAGE_TYPES } from '@/lib/image-types';
import { PHOTO_TYPES, type PhotoType } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface DraftPhoto {
  id: string;
  file: File;
  preview: string;
  type: PhotoType;
}

const MAX_PHOTO_BYTES = 20 * 1024 * 1024;

// Photos for an item that does not exist yet: nothing is uploaded until the form is sent. The
// first photo is the cover; the others are added to the item right after it is created.
export function PhotoPicker({
  photos,
  onChange,
  disabled = false,
  limit = 10,
  chooseCover = true,
}: {
  photos: DraftPhoto[];
  onChange: (photos: DraftPhoto[]) => void;
  disabled?: boolean;
  limit?: number;
  chooseCover?: boolean;
}) {
  const t = useTranslations('wardrobe.photos');
  const viewLabel = usePhotoTypeLabel();
  const ownedUrls = useRef(new Set<string>());

  // Object URLs are released as soon as their photo leaves the list, and all of them on unmount.
  useEffect(() => {
    const kept = new Set(photos.map((photo) => photo.preview));
    ownedUrls.current.forEach((url) => {
      if (!kept.has(url)) {
        URL.revokeObjectURL(url);
        ownedUrls.current.delete(url);
      }
    });
  }, [photos]);
  useEffect(() => {
    const owned = ownedUrls.current;
    return () => owned.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    accept: ACCEPTED_IMAGE_TYPES,
    multiple: true,
    maxSize: MAX_PHOTO_BYTES,
    disabled: disabled || photos.length >= limit,
    onDrop: (files) => {
      const taken = photos.map((photo) => photo.type);
      const added = files.slice(0, Math.max(0, limit - photos.length)).map((file) => {
        const type = nextFreeView(taken) ?? 'other';
        taken.push(type);
        const preview = URL.createObjectURL(file);
        ownedUrls.current.add(preview);
        return { id: crypto.randomUUID(), file, preview, type };
      });
      onChange([...photos, ...added]);
    },
  });

  const move = (from: number, to: number) => {
    const next = [...photos];
    const [photo] = next.splice(from, 1);
    next.splice(to, 0, photo);
    onChange(next);
  };

  const setType = (id: string, type: PhotoType) =>
    onChange(
      photos.map((photo) => {
        if (photo.id === id) return { ...photo, type };
        // Only one front and one back: the photo that had the label falls back to "other".
        if ((type === 'front' || type === 'back') && photo.type === type) return { ...photo, type: 'other' };
        return photo;
      })
    );

  return (
    <div className="space-y-3">
      {photos.length < limit && (
        <div
          {...getRootProps()}
          className={cn(
            'cursor-pointer rounded-xl border-2 border-dashed p-5 text-center transition-colors',
            isDragActive ? 'border-primary bg-primary/10' : 'border-primary/30 bg-primary/5 hover:border-primary/60'
          )}
        >
          <input {...getInputProps()} aria-label={t('add')} />
          <Upload className="mx-auto mb-2 h-6 w-6 text-primary" />
          <p className="text-sm font-medium">{t('add')}</p>
          <p className="text-xs text-muted-foreground">{t('pickerHint', { count: limit })}</p>
        </div>
      )}
      {fileRejections.length > 0 && (
        <p role="alert" className="text-sm text-destructive">
          {t('invalid')}
        </p>
      )}
      {photos.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {photos.map((photo, index) => (
            <div
              key={photo.id}
              className={cn(
                'min-w-0 space-y-1.5 rounded-lg border bg-card p-1.5',
                chooseCover && index === 0 && 'border-primary/50 ring-1 ring-primary/20'
              )}
            >
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
                <img src={photo.preview} alt={photo.file.name} className="aspect-square w-full rounded-md bg-muted garment-fit" />
                {chooseCover && index === 0 && (
                  <span className="absolute left-1 top-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
                    {t('cover')}
                  </span>
                )}
              </div>
              <select
                aria-label={t('type')}
                disabled={disabled}
                value={photo.type}
                className="h-9 w-full rounded-md border bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onChange={(e) => setType(photo.id, e.target.value as PhotoType)}
              >
                {PHOTO_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {viewLabel(type)}
                  </option>
                ))}
              </select>
              <div className="flex items-center justify-between gap-0.5">
                {chooseCover && (
                  <Button
                    type="button"
                    size="icon"
                    variant={index === 0 ? 'secondary' : 'ghost'}
                    className="h-8 w-8"
                    disabled={disabled}
                    aria-label={t('cover')}
                    aria-pressed={index === 0}
                    onClick={() => move(index, 0)}
                  >
                    <Star className={cn('h-4 w-4', index === 0 && 'fill-current text-primary')} />
                  </Button>
                )}
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={disabled || index === 0}
                  aria-label={t('previous')}
                  onClick={() => move(index, index - 1)}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={disabled || index === photos.length - 1}
                  aria-label={t('next')}
                  onClick={() => move(index, index + 1)}
                >
                  <ArrowRight className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-destructive hover:text-destructive"
                  disabled={disabled}
                  aria-label={t('remove')}
                  onClick={() => onChange(photos.filter((p) => p.id !== photo.id))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
