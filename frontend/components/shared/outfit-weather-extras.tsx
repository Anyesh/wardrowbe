'use client';

import Image from 'next/image';
import Link from 'next/link';
import { Shirt } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { useTypeLabel } from '@/lib/hooks/use-translated-constants';
import type { OutfitExtraItem } from '@/lib/types';

interface OutfitWeatherExtrasProps {
  ifCooler?: OutfitExtraItem | null;
  ifWarmer?: OutfitExtraItem | null;
}

function ExtraRow({
  item,
  messageKey,
}: {
  item: OutfitExtraItem;
  messageKey: 'ifCooler' | 'ifWarmer';
}) {
  const t = useTranslations('outfits.weatherExtras');
  const typeLabel = useTypeLabel();
  const label = item.name || typeLabel(item.type);
  return (
    <li>
      <Link
        href={`/dashboard/wardrobe?item=${item.id}`}
        className="flex items-center gap-2.5 rounded-lg border bg-muted/40 p-1.5 pr-3 text-xs sm:text-sm hover:bg-muted/70 transition-colors"
      >
        <span className="relative h-9 w-9 flex-shrink-0 overflow-hidden rounded-md bg-muted">
          {item.thumbnail_url ? (
            <Image src={item.thumbnail_url} alt={label} fill className="object-cover" sizes="36px" />
          ) : (
            <span className="flex h-full w-full items-center justify-center">
              <Shirt className="h-4 w-4 text-muted-foreground/50" />
            </span>
          )}
        </span>
        <span className="min-w-0 truncate">{t(messageKey, { item: label })}</span>
      </Link>
    </li>
  );
}

export function OutfitWeatherExtras({ ifCooler, ifWarmer }: OutfitWeatherExtrasProps) {
  if (!ifCooler && !ifWarmer) return null;
  return (
    <ul className="space-y-1.5" data-testid="outfit-weather-extras">
      {ifCooler && <ExtraRow item={ifCooler} messageKey="ifCooler" />}
      {ifWarmer && <ExtraRow item={ifWarmer} messageKey="ifWarmer" />}
    </ul>
  );
}
