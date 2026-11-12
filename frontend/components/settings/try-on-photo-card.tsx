'use client';

import { useRef, useState } from 'react';
import Image from 'next/image';
import { Loader2, Shirt, Trash2, Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ACCEPTED_IMAGE_INPUT } from '@/lib/image-types';
import { useFeatures, useTryOnEnabled } from '@/lib/hooks/use-features';
import {
  useDeleteTryOnPhoto,
  useTryOnPhoto,
  useUploadTryOnPhoto,
} from '@/lib/hooks/use-try-on';

// Self-contained on purpose: the settings page saves its form with one button, while this
// card saves each change as it happens.
export function TryOnPhotoCard() {
  const enabled = useTryOnEnabled();
  const features = useFeatures();
  if (enabled) return <TryOnPhotoCardContent />;
  // Switched off by the operator: whoever still has a saved photo can see and remove it.
  if (features.data) return <TryOnPhotoCardContent featureOff />;
  return null;
}

function TryOnPhotoCardContent({ featureOff = false }: { featureOff?: boolean }) {
  const t = useTranslations('settings.tryOnPhoto');
  const tc = useTranslations('common');
  const photo = useTryOnPhoto({ whenDisabled: featureOff });
  const upload = useUploadTryOnPhoto();
  const remove = useDeleteTryOnPhoto();
  const inputRef = useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const save = (file: File) =>
    upload.mutate(file, {
      onSuccess: () => toast.success(t('saved')),
      onError: () => toast.error(t('uploadError')),
    });

  const onFileChosen = (file: File | undefined) => {
    if (inputRef.current) inputRef.current.value = '';
    if (!file || !photo.isSuccess) return;
    // Replacing deletes the try-ons drawn from the old photo, so it is confirmed.
    if (photo.data) setPendingFile(file);
    else save(file);
  };

  const onRemove = () =>
    remove.mutate(undefined, {
      onSuccess: () => toast.success(t('removed')),
      onError: () => toast.error(t('removeError')),
    });

  const busy = upload.isPending || remove.isPending;

  // Nothing to offer once try-on is off and there is no photo to remove.
  if (featureOff && !photo.data) return null;

  return (
    <Card id="try-on-photo">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shirt className="h-5 w-5" />
          {t('title')}
        </CardTitle>
        <CardDescription>{featureOff ? t('disabledNotice') : t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!featureOff && (
          <>
            <p className="text-sm text-muted-foreground">{t('guidance')}</p>
            <p className="text-sm text-muted-foreground">{t('privacy')}</p>
          </>
        )}

        {photo.isError && (
          <p role="alert" className="text-sm text-destructive">
            {t('loadError')}
          </p>
        )}

        {photo.data && (
          <div className="relative aspect-[3/4] w-full max-w-[200px] overflow-hidden rounded-lg border bg-muted">
            <Image
              src={(photo.data.medium_url || photo.data.image_url)!}
              alt={t('photoAlt')}
              fill
              className="object-contain"
              sizes="200px"
              unoptimized
            />
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_IMAGE_INPUT}
          className="hidden"
          data-testid="try-on-photo-input"
          onChange={(e) => onFileChosen(e.target.files?.[0])}
        />

        <div className="flex flex-wrap gap-2">
          {!featureOff && (
            // Until the photo is known, a replacement could skip its confirmation.
            <Button
              variant="outline"
              onClick={() => inputRef.current?.click()}
              disabled={busy || !photo.isSuccess}
            >
              {upload.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Upload className="h-4 w-4 mr-2" />
              )}
              {photo.data ? t('replace') : t('upload')}
            </Button>
          )}
          {photo.data && (
            <Button variant="ghost" onClick={() => setConfirmRemove(true)} disabled={busy}>
              <Trash2 className="h-4 w-4 mr-2" />
              {t('remove')}
            </Button>
          )}
        </div>
      </CardContent>

      <AlertDialog open={confirmRemove} onOpenChange={setConfirmRemove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('removeConfirm.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('removeConfirm.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tc('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={onRemove}>{t('removeConfirm.confirm')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!pendingFile} onOpenChange={(open) => !open && setPendingFile(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('replaceConfirm.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('replaceConfirm.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tc('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingFile) save(pendingFile);
                setPendingFile(null);
              }}
            >
              {t('replaceConfirm.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
