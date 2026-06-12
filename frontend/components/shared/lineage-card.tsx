'use client';

import Link from 'next/link';
import { ArrowRight, BookmarkCheck } from 'lucide-react';
import { format, parseISO } from 'date-fns';

import { Card, CardContent } from '@/components/ui/card';
import { useOutfit } from '@/lib/hooks/use-outfits';
import type { Outfit } from '@/lib/hooks/use-outfits';
import { useTranslations } from 'next-intl';

interface LineageCardProps {
  outfit: Outfit;
}

export function LineageCard({ outfit }: LineageCardProps) {
  const t = useTranslations('studio.lineage');
  const replacesId = outfit.replaces_outfit_id;
  const clonedFromId = outfit.cloned_from_outfit_id;

  const { data: referenced } = useOutfit(replacesId ?? clonedFromId ?? undefined);

  if (!replacesId && !clonedFromId) return null;
  if (!referenced) return null;

  const isReplacement = !!replacesId;
  const Icon = isReplacement ? ArrowRight : BookmarkCheck;

  const label = isReplacement
    ? referenced.scheduled_for
      ? t('replacesWithDate', { occasion: referenced.occasion, date: format(parseISO(referenced.scheduled_for), 'MMM d') })
      : t('replaces', { occasion: referenced.occasion })
    : t('fromLookbook', { name: referenced.name || referenced.occasion });

  return (
    <Card className="border-muted bg-muted/30">
      <CardContent className="p-3">
        <Link
          href={`/dashboard/outfits/${referenced.id}`}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Icon className="h-4 w-4 shrink-0" />
          <span className="truncate">{label}</span>
        </Link>
      </CardContent>
    </Card>
  );
}
