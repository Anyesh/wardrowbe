'use client';

import Link from 'next/link';
import Image from 'next/image';
import { formatDistanceToNow, parseISO } from 'date-fns';
import {
  BookmarkCheck,
  Layers,
  RefreshCw,
  Shirt,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { Outfit } from '@/lib/hooks/use-outfits';

interface OutfitCardProps {
  outfit: Outfit;
  onClick?: () => void;
}

function getSourceBadge(outfit: Outfit): {
  label: string;
  icon: React.ReactNode;
  className: string;
} | null {
  if (outfit.replaces_outfit_id) {
    return {
      label: 'Replacement',
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
      label: 'Worn',
      icon: <BookmarkCheck className="h-3 w-3" />,
      className: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    };
  }
  if (outfit.source === 'manual') {
    return {
      label: 'Studio',
      icon: <Shirt className="h-3 w-3" />,
      className: 'bg-purple-100 text-purple-700 border-purple-200',
    };
  }
  if (outfit.source === 'pairing') {
    return {
      label: 'Pairing',
      icon: <Layers className="h-3 w-3" />,
      className: 'bg-amber-100 text-amber-700 border-amber-200',
    };
  }
  return {
    label: 'AI',
    icon: <Sparkles className="h-3 w-3" />,
    className: 'bg-blue-100 text-blue-700 border-blue-200',
  };
}

function getCardTitle(outfit: Outfit): string {
  if (outfit.name) return outfit.name;
  if (outfit.highlights && outfit.highlights.length > 0) {
    return outfit.highlights[0];
  }
  const occasion =
    outfit.occasion.charAt(0).toUpperCase() + outfit.occasion.slice(1);
  return `${occasion} outfit`;
}

function getMetaLabel(outfit: Outfit): string {
  if (!outfit.scheduled_for) return 'Lookbook template';
  try {
    return formatDistanceToNow(parseISO(outfit.scheduled_for), {
      addSuffix: true,
    });
  } catch {
    return outfit.scheduled_for;
  }
}

export function OutfitCard({ outfit, onClick }: OutfitCardProps) {
  const badge = getSourceBadge(outfit);
  const visibleItems = outfit.items.slice(0, 4);
  const overflow = outfit.items.length - visibleItems.length;

  const content = (
    <Card
      className={cn(
        'overflow-hidden transition-all hover:shadow-md',
        onClick && 'cursor-pointer'
      )}
      onClick={onClick}
    >
      <CardContent className="p-0">
        <div className="relative aspect-[5/4] bg-muted">
          <div className="absolute inset-0 grid grid-cols-4 gap-0.5 p-2">
            {visibleItems.map((item, idx) => (
              <div
                key={`${item.id}-${idx}`}
                className="relative rounded overflow-hidden bg-background"
              >
                {item.thumbnail_url || item.image_url ? (
                  <Image
                    src={(item.thumbnail_url || item.image_url)!}
                    alt={item.name || item.type}
                    fill
                    className="object-cover"
                    sizes="(max-width: 640px) 25vw, 15vw"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-[10px] text-muted-foreground">
                      {item.type}
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
            {getCardTitle(outfit)}
          </h3>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <Badge variant="outline" className="capitalize">
              {outfit.occasion}
            </Badge>
            <span>{getMetaLabel(outfit)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (onClick) return content;
  return (
    <Link href={`/dashboard/outfits/${outfit.id}`} className="block">
      {content}
    </Link>
  );
}
