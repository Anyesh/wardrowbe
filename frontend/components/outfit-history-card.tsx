'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Calendar, Zap, Edit3, ThumbsUp, ThumbsDown, Clock, Eye, Star, ArrowRight, Shirt, Users, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { useAcceptOutfit, useRejectOutfit, type Outfit, type OutfitSource, type WoreInsteadItem } from '@/lib/hooks/use-outfits';
import Image from 'next/image';
import { useTranslations } from 'next-intl';

function StatusIcon({ status }: { status: Outfit['status'] }) {
  switch (status) {
    case 'accepted':
      return <ThumbsUp className="h-4 w-4 text-green-500" />;
    case 'rejected':
      return <ThumbsDown className="h-4 w-4 text-red-500" />;
    case 'viewed':
      return <Eye className="h-4 w-4 text-blue-500" />;
    case 'sent':
    case 'pending':
      return <Clock className="h-4 w-4 text-muted-foreground" />;
    case 'expired':
      return <Clock className="h-4 w-4 text-orange-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: Outfit['status'] }) {
  const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    accepted: 'default',
    rejected: 'destructive',
    viewed: 'secondary',
    sent: 'outline',
    pending: 'outline',
    expired: 'secondary',
  };

  return (
    <Badge variant={variants[status] || 'outline'} className="capitalize">
      {status}
    </Badge>
  );
}

function SourceBadge({ source }: { source: OutfitSource }) {
  const t = useTranslations('cards.outfitHistory');
  const config: Record<OutfitSource, { icon: typeof Calendar; label: string; className: string }> = {
    scheduled: {
      icon: Calendar,
      label: t('scheduled'),
      className: 'bg-primary/10 text-primary border-primary/20',
    },
    on_demand: {
      icon: Zap,
      label: t('onDemand'),
      className: 'bg-orange-500/10 text-orange-600 border-orange-500/20',
    },
    manual: {
      icon: Edit3,
      label: t('manual'),
      className: 'bg-purple-500/10 text-purple-600 border-purple-500/20',
    },
    pairing: {
      icon: Zap,
      label: t('pairing'),
      className: 'bg-violet-500/10 text-violet-600 border-violet-500/20',
    },
  };

  const { icon: Icon, label, className } = config[source];

  return (
    <Badge variant="outline" className={className}>
      <Icon className="h-3 w-3 mr-1" />
      {label}
    </Badge>
  );
}

function StarRating({ rating, size = 'sm' }: { rating: number; size?: 'sm' | 'lg' }) {
  const sizeClass = size === 'lg' ? 'h-5 w-5' : 'h-3.5 w-3.5';

  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={`${sizeClass} ${star <= rating ? 'fill-yellow-400 text-yellow-400' : 'text-muted-foreground/30'}`}
        />
      ))}
    </div>
  );
}

interface OutfitHistoryCardProps {
  outfit: Outfit;
  onFeedback: () => void;
  onPreview?: () => void;
}

export function OutfitHistoryCard({ outfit, onFeedback, onPreview }: OutfitHistoryCardProps) {
  const t = useTranslations('cards.outfitHistory');
  const acceptOutfit = useAcceptOutfit();
  const rejectOutfit = useRejectOutfit();
  const [previewItem, setPreviewItem] = useState<WoreInsteadItem | null>(null);

  const handleAccept = async () => {
    try {
      await acceptOutfit.mutateAsync(outfit.id);
      toast.success(t('outfitAccepted'));
    } catch {
      toast.error(t('acceptFailed'));
    }
  };

  const handleReject = async () => {
    try {
      await rejectOutfit.mutateAsync(outfit.id);
      toast.success(t('outfitRejected'));
    } catch {
      toast.error(t('rejectFailed'));
    }
  };

  const isPending = outfit.status === 'pending' || outfit.status === 'sent' || outfit.status === 'viewed';

  return (
    <Card className="overflow-hidden h-full flex flex-col">
      <CardContent className="p-3 flex flex-col flex-1">
        {/* Header with source badge and status */}
        <div className="flex items-center justify-between mb-2">
          <SourceBadge source={outfit.source} />
          <div className="flex items-center gap-1.5">
            <Badge variant="secondary" className="capitalize text-xs">
              {outfit.occasion}
            </Badge>
            <StatusIcon status={outfit.status} />
          </div>
        </div>

        {/* Item thumbnails - clickable to preview */}
        <button
          type="button"
          onClick={onPreview}
          className="flex gap-2 text-left w-full group"
        >
          {outfit.items.map((item) => (
            <div
              key={item.id}
              className="w-16 h-16 rounded-lg bg-muted overflow-hidden relative border shadow-sm group-hover:shadow-md transition-shadow"
            >
              {item.thumbnail_url ? (
                <Image
                  src={item.thumbnail_url}
                  alt={item.name || item.type}
                  fill
                  className="object-cover"
                  sizes="64px"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                  {item.type}
                </div>
              )}
            </div>
          ))}
        </button>

        {/* Inline feedback display */}
        {outfit.feedback && (outfit.feedback.rating || outfit.feedback.comment) && (
          <div className="mt-2 pt-2 border-t">
            <div className="flex items-center gap-2">
              {outfit.feedback.rating && (
                <StarRating rating={outfit.feedback.rating} />
              )}
              {outfit.feedback.comment && (
                <p className="text-xs text-muted-foreground truncate flex-1">
                  &ldquo;{outfit.feedback.comment}&rdquo;
                </p>
              )}
            </div>
          </div>
        )}

        {/* Wore instead display */}
        {outfit.feedback?.actually_worn === false && (
          <div className="mt-2 pt-2 border-t">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <span>{t('didntWearThis')}</span>
              {outfit.feedback.wore_instead_items && outfit.feedback.wore_instead_items.length > 0 && (
                <>
                  <ArrowRight className="h-3 w-3" />
                  <span className="text-foreground font-medium">{t('woreInstead')}</span>
                </>
              )}
            </div>
            {outfit.feedback.wore_instead_items && outfit.feedback.wore_instead_items.length > 0 && (
              <div className="flex gap-2 flex-wrap">
                {outfit.feedback.wore_instead_items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setPreviewItem(item)}
                    className="w-14 h-14 rounded-lg bg-muted overflow-hidden relative border hover:ring-2 ring-primary transition-all"
                    title={item.name || item.type}
                  >
                    {item.thumbnail_url ? (
                      <Image
                        src={item.thumbnail_url}
                        alt={item.name || item.type}
                        fill
                        className="object-cover"
                        sizes="56px"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Shirt className="h-5 w-5 text-muted-foreground" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Family ratings summary */}
        {outfit.family_rating_count != null && outfit.family_rating_count > 0 && (
          <div className="mt-2 pt-2 border-t">
            <div className="flex items-center gap-2 text-xs">
              <Users className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-muted-foreground">{t('familyLabel')}</span>
              <StarRating rating={Math.round(outfit.family_rating_average ?? 0)} />
              <span className="text-muted-foreground">
                ({outfit.family_rating_count})
              </span>
            </div>
          </div>
        )}

        {/* Details section */}
        {(outfit.reasoning || outfit.style_notes || (outfit.highlights && outfit.highlights.length > 0)) && (
          <div className="mt-2 space-y-2 text-xs flex-1">
            {outfit.reasoning && (
              <p className="font-medium text-foreground">{outfit.reasoning}</p>
            )}
            {outfit.highlights && outfit.highlights.length > 0 && (
              <ul className="space-y-0.5">
                {outfit.highlights.map((highlight, index) => (
                  <li key={index} className="flex items-start gap-1.5 text-muted-foreground">
                    <span className="text-primary mt-0.5">•</span>
                    <span>{highlight}</span>
                  </li>
                ))}
              </ul>
            )}
            {outfit.style_notes && (
              <div className="p-2 bg-muted rounded border">
                <p className="text-muted-foreground">
                  <span className="font-medium text-foreground">{t('tip')}</span> {outfit.style_notes}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Action buttons - pushed to bottom */}
        <div className="mt-auto pt-3">
          {isPending && (
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                className="flex-1 h-8 text-xs"
                onClick={handleReject}
                disabled={rejectOutfit.isPending}
              >
                <ThumbsDown className="h-3 w-3 mr-1" />
                {t('reject')}
              </Button>
              <Button
                size="sm"
                className="flex-1 h-8 text-xs"
                onClick={handleAccept}
                disabled={acceptOutfit.isPending}
              >
                <ThumbsUp className="h-3 w-3 mr-1" />
                {t('accept')}
              </Button>
            </div>
          )}

          {outfit.status === 'accepted' && outfit.feedback?.actually_worn !== false && (
            <Button
              size="sm"
              variant="outline"
              className="w-full h-8 text-xs"
              onClick={onFeedback}
            >
              <Star className="h-3 w-3 mr-1" />
              {outfit.feedback?.rating ? t('update') : t('rate')}
            </Button>
          )}
        </div>
      </CardContent>

      {/* Wore instead item preview modal */}
      <Dialog open={!!previewItem} onOpenChange={(open) => !open && setPreviewItem(null)}>
        <DialogContent className="sm:max-w-md p-0 overflow-hidden [&>button]:hidden">
          <DialogHeader className="p-4 pb-2">
            <DialogTitle>{previewItem?.name || previewItem?.type || 'Item'}</DialogTitle>
          </DialogHeader>
          <div className="relative bg-muted">
            <Link href={`/dashboard/wardrobe?item=${previewItem?.id}`} className="block">
              <div className="relative aspect-square w-full max-h-[350px]">
                {previewItem?.thumbnail_url ? (
                  <Image
                    src={previewItem.thumbnail_url}
                    alt={previewItem.name || previewItem.type}
                    fill
                    className="object-contain"
                    sizes="(max-width: 448px) 100vw, 448px"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <Shirt className="h-16 w-16 text-muted-foreground" />
                  </div>
                )}
              </div>
            </Link>
          </div>
          <div className="p-4 pt-2 space-y-3">
            <Badge variant="secondary" className="capitalize">
              {previewItem?.type}
            </Badge>
            <Button variant="outline" size="sm" className="w-full h-8 text-xs gap-1.5" asChild>
              <Link href={`/dashboard/wardrobe?item=${previewItem?.id}`}>
                <ExternalLink className="h-3 w-3" />
                {t('viewItemDetails')}
              </Link>
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
