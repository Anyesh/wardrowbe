'use client';

import Image from 'next/image';
import Link from 'next/link';
import { Loader2, RefreshCw, Shirt, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useTryOnEnabled } from '@/lib/hooks/use-features';
import {
  tryOnErrorCode,
  useDeleteTryOn,
  useGenerateTryOn,
  useOutfitTryOn,
  useTryOnPhoto,
} from '@/lib/hooks/use-try-on';
import { ApiError } from '@/lib/api';

const ERROR_KEYS: Record<string, string> = {
  TRY_ON_NO_IMAGE: 'errors.noImage',
  TRY_ON_DAILY_LIMIT: 'errors.dailyLimit',
  TRY_ON_ITEM_IMAGE_MISSING: 'errors.itemImageMissing',
  TRY_ON_NO_PHOTO: 'errors.noPhoto',
  TRY_ON_IN_PROGRESS: 'errors.inProgress',
};

interface TryOnPanelProps {
  outfitId: string;
}

export function TryOnPanel({ outfitId }: TryOnPanelProps) {
  const enabled = useTryOnEnabled();
  if (!enabled) return null;
  return <TryOnPanelContent outfitId={outfitId} />;
}

function TryOnPanelContent({ outfitId }: TryOnPanelProps) {
  const t = useTranslations('outfits.tryOn');
  const photo = useTryOnPhoto();
  const tryOn = useOutfitTryOn(outfitId);
  const generate = useGenerateTryOn();
  const remove = useDeleteTryOn();

  const errorMessage = (code: string | null | undefined) =>
    t((ERROR_KEYS[code ?? ''] ?? 'errors.generic') as 'errors.generic');

  const start = (regenerate: boolean) => {
    generate.mutate(
      { outfitId, regenerate },
      {
        onError: (error) => {
          const code = tryOnErrorCode(error);
          if (code === 'TRY_ON_IN_PROGRESS') return;
          if (error instanceof ApiError && error.status === 429 && code !== 'TRY_ON_DAILY_LIMIT') {
            toast.error(t('errors.rateLimited'));
            return;
          }
          toast.error(errorMessage(code));
        },
      }
    );
  };

  const onDelete = () =>
    remove.mutate(outfitId, { onError: () => toast.error(t('deleteError')) });

  if (photo.isLoading || tryOn.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
        </CardContent>
      </Card>
    );
  }

  const current = tryOn.data;
  const pending = current?.status === 'pending' || generate.isPending;
  const hasPhoto = !!photo.data;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          {t('title')}
        </h2>

        {!hasPhoto && !pending && current?.status !== 'ready' ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('needsPhoto')}</p>
            <Button variant="outline" asChild>
              <Link href="/dashboard/settings#try-on-photo">
                <Shirt className="h-4 w-4 mr-2" />
                {t('addPhoto')}
              </Link>
            </Button>
          </div>
        ) : pending ? (
          <div
            role="status"
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {t('drawing')}
          </div>
        ) : current?.status === 'ready' && current.image_url ? (
          <div className="space-y-3">
            <div className="relative mx-auto aspect-[3/4] w-full max-w-xs overflow-hidden rounded-lg border bg-muted">
              <Image
                src={(current.medium_url || current.image_url)!}
                alt={t('imageAlt')}
                fill
                className="object-contain"
                sizes="(max-width: 640px) 80vw, 320px"
                unoptimized
              />
            </div>
            {current.stale && <p className="text-xs text-muted-foreground">{t('stale')}</p>}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => start(true)}>
                <RefreshCw className="h-4 w-4 mr-2" />
                {t('regenerate')}
              </Button>
              <Button variant="ghost" onClick={onDelete} disabled={remove.isPending}>
                <Trash2 className="h-4 w-4 mr-2" />
                {t('delete')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {current?.status === 'failed' && (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(current.error_code)}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => start(current?.status === 'failed')}>
                <Shirt className="h-4 w-4 mr-2" />
                {t('seeIt')}
              </Button>
              {current && (
                <Button variant="ghost" onClick={onDelete} disabled={remove.isPending}>
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('delete')}
                </Button>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
