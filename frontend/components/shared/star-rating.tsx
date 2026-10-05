'use client';

import { useState } from 'react';
import { Star } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { RATING_MAX } from '@/lib/generated/scales';
import { RATING_STARS } from '@/lib/rating';
import { cn } from '@/lib/utils';

const FILLED = 'fill-yellow-400 text-yellow-400';

interface StarRatingInputProps {
  value: number;
  onChange: (rating: number) => void;
  starClassName?: string;
}

export function StarRatingInput({ value, onChange, starClassName = 'h-6 w-6' }: StarRatingInputProps) {
  const t = useTranslations('common');
  const [hovered, setHovered] = useState(0);

  return (
    <div className="flex gap-1" onMouseLeave={() => setHovered(0)}>
      {RATING_STARS.map((star) => (
        <button
          key={star}
          type="button"
          aria-label={t('rateStars', { count: star })}
          aria-pressed={star === value}
          onMouseEnter={() => setHovered(star)}
          onClick={() => onChange(star)}
          className="rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 hover:scale-110 transition-transform"
        >
          <Star
            aria-hidden="true"
            className={cn(
              starClassName,
              'transition-colors',
              star <= (hovered || value)
                ? FILLED
                : 'text-muted-foreground/30 hover:text-muted-foreground/50'
            )}
          />
        </button>
      ))}
    </div>
  );
}

interface StarRatingDisplayProps {
  value: number;
  starClassName?: string;
}

export function StarRatingDisplay({ value, starClassName = 'h-3.5 w-3.5' }: StarRatingDisplayProps) {
  const t = useTranslations('common');

  return (
    <div
      role="img"
      aria-label={t('ratedStars', { rating: value, max: RATING_MAX })}
      className="flex gap-0.5"
    >
      {RATING_STARS.map((star) => (
        <Star
          key={star}
          aria-hidden="true"
          className={cn(starClassName, star <= value ? FILLED : 'text-muted-foreground/30')}
        />
      ))}
    </div>
  );
}
