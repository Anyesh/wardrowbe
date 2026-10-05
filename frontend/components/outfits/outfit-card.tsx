'use client';

import Link from 'next/link';
import Image from 'next/image';
import {
  BookmarkCheck,
  Bot,
  Layers,
  RefreshCw,
  Shirt,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { cn, formatRelativeDate } from '@/lib/utils';
import type { Outfit } from '@/lib/hooks/use-outfits';
import { useUserToday } from '@/lib/hooks/use-user';
import { useOccasionLabel, useTypeLabel } from '@/lib/hooks/use-translated-constants';
import { useLocale, useTranslations, type createTranslator } from 'next-intl';
import type outfitsMessages from '@/messages/en/outfits.json';

interface OutfitCardProps {
  outfit: Outfit;
  onClick?: () => void;
  selectMode?: boolean;
  selected?: boolean;
  onSelect?: (id: string, checked: boolean) => void;
}

// Typed against the en catalog because the app does not register its messages with next-intl,
// so useTranslations alone accepts any string and a mistyped key would only show at render.
export type OutfitCardTranslator = ReturnType<
  typeof createTranslator<{ outfits: typeof outfitsMessages }, 'outfits.cards'>
>;

function getSourceBadge(outfit: Outfit, t: OutfitCardTranslator): {
  label: string;
  icon: React.ReactNode;
  className: string;
} | null {
  if (outfit.replaces_outfit_id) {
    return {
      label: t('replacement'),
      icon: <RefreshCw className="h-3 w-3" />,
      className: 'bg-orange-100 text-orange-700 border-orange-200',
    };
  }
  if (
    outfit.cloned_from_outfit_id &&
    outfit.source === 'manual' &&
    outfit.scheduled_for
  ) {
    return {
      label: t('worn'),
      icon: <BookmarkCheck className="h-3 w-3" />,
      className: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    };
  }
  if (outfit.source === 'manual') {
    return {
      label: t('studio'),
      icon: <Shirt className="h-3 w-3" />,
      className: 'bg-purple-100 text-purple-700 border-purple-200',
    };
  }
  if (outfit.source === 'pairing') {
    return {
      label: t('pairing'),
      icon: <Layers className="h-3 w-3" />,
      className: 'bg-amber-100 text-amber-700 border-amber-200',
    };
  }
  if (outfit.source === 'external') {
    return {
      label: t('external'),
      icon: <Bot className="h-3 w-3" />,
      className: 'bg-teal-100 text-teal-700 border-teal-200',
    };
  }
  return {
    label: t('ai'),
    icon: <Sparkles className="h-3 w-3" />,
    className: 'bg-blue-100 text-blue-700 border-blue-200',
  };
}

function getCardTitle(outfit: Outfit, t: OutfitCardTranslator, occasionLabel: (value: string) => string): string {
  if (outfit.name) return outfit.name;
  if (outfit.reasoning) return outfit.reasoning;
  if (outfit.highlights && outfit.highlights.length > 0) {
    return outfit.highlights[0];
  }
  return t('outfitFallback', { occasion: occasionLabel(outfit.occasion) });
}
function getMetaLabel(outfit: Outfit, t: OutfitCardTranslator, locale: string, today: string): string {
  if (!outfit.scheduled_for) return t('lookbookTemplate');
  try {
    return formatRelativeDate(outfit.scheduled_for, locale, today);
  } catch {
    return outfit.scheduled_for;
  }
}

export function OutfitCard({ outfit, onClick, selectMode, selected, onSelect }: OutfitCardProps) {
  const typeLabel = useTypeLabel();
  const t: OutfitCardTranslator = useTranslations('outfits.cards');
  const locale = useLocale();
  const getUserToday = useUserToday();
  const occasionLabel = useOccasionLabel();
  const badge = getSourceBadge(outfit, t);
  const visibleItems = outfit.items.slice(0, 4);
  const overflow = outfit.items.length - visibleItems.length;

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  const handleCardClick = selectMode
    ? () => onSelect?.(outfit.id, !selected)
    : onClick;

  const content = (
    <Card
      className={cn(
        'overflow-hidden transition-all hover:shadow-md',
        handleCardClick && 'cursor-pointer',
        selectMode && selected && 'ring-2 ring-primary shadow-md'
      )}
      onClick={handleCardClick}
    >
      <CardContent className="p-0">
        <div className="relative aspect-[5/4] bg-muted">
          {selectMode && (
            <div
              className="absolute top-2 left-2 z-10"
              onClick={handleCheckboxClick}
            >
              <Checkbox
                checked={!!selected}
                onCheckedChange={(checked) => onSelect?.(outfit.id, checked === true)}
                className="bg-background/80 backdrop-blur-sm"
              />
            </div>
          )}
          <div className="absolute inset-0 grid grid-cols-4 gap-0.5 p-2">
            {visibleItems.map((item, idx) => (
              <div
                key={`${item.id}-${idx}`}
                className="relative rounded overflow-hidden bg-background"
              >
                {item.thumbnail_url || item.image_url ? (
                  <Image
                    src={(item.thumbnail_url || item.image_url)!}
                    alt={item.name || typeLabel(item.type)}
                    fill
                    className="object-cover"
                    sizes="(max-width: 640px) 25vw, 15vw"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-[10px] text-muted-foreground">
                      {typeLabel(item.type)}
                    </span>
                  </div>
                )}
              </div>
            ))}
            {overflow > 0 && (
              <div className="relative rounded overflow-hidden bg-background flex items-center justify-center">
                <span className="text-sm font-medium text-muted-foreground">
                  +{overflow}
                </span>
              </div>
            )}
          </div>
          {badge && (
            <div
              className={cn(
                'absolute top-2 right-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium',
                badge.className
              )}
            >
              {badge.icon}
              <span>{badge.label}</span>
            </div>
          )}
        </div>
        <div className="p-3 space-y-1">
          <h3 className="text-sm font-semibold leading-tight truncate">
            {getCardTitle(outfit, t, occasionLabel)}
          </h3>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <Badge variant="outline" className="capitalize">
              {occasionLabel(outfit.occasion)}
            </Badge>
            <span>{getMetaLabel(outfit, t, locale, getUserToday())}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (selectMode || onClick) return content;
  return (
    <Link href={`/dashboard/outfits/${outfit.id}`} className="block">
      {content}
    </Link>
  );
}
