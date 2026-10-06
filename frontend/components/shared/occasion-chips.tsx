'use client';

import React from 'react';
import {
  Briefcase,
  Dumbbell,
  GlassWater,
  Heart,
  Shirt,
  Tag,
  TreePine,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { useOccasionOptions } from '@/lib/hooks/use-translated-constants';
import type { FeaturedOccasion } from '@/lib/types';

export const OCCASION_CONFIG: Record<
  FeaturedOccasion,
  { icon: React.ReactNode; color: string }
> = {
  casual: {
    icon: <Shirt className="h-4 w-4" />,
    color:
      'hover:border-blue-400 hover:bg-blue-50 data-[selected=true]:border-blue-500 data-[selected=true]:bg-blue-50 data-[selected=true]:text-blue-700',
  },
  office: {
    icon: <Briefcase className="h-4 w-4" />,
    color:
      'hover:border-slate-400 hover:bg-slate-50 data-[selected=true]:border-slate-500 data-[selected=true]:bg-slate-50 data-[selected=true]:text-slate-700',
  },
  formal: {
    icon: <GlassWater className="h-4 w-4" />,
    color:
      'hover:border-purple-400 hover:bg-purple-50 data-[selected=true]:border-purple-500 data-[selected=true]:bg-purple-50 data-[selected=true]:text-purple-700',
  },
  date: {
    icon: <Heart className="h-4 w-4" />,
    color:
      'hover:border-rose-400 hover:bg-rose-50 data-[selected=true]:border-rose-500 data-[selected=true]:bg-rose-50 data-[selected=true]:text-rose-700',
  },
  sporty: {
    icon: <Dumbbell className="h-4 w-4" />,
    color:
      'hover:border-orange-400 hover:bg-orange-50 data-[selected=true]:border-orange-500 data-[selected=true]:bg-orange-50 data-[selected=true]:text-orange-700',
  },
  outdoor: {
    icon: <TreePine className="h-4 w-4" />,
    color:
      'hover:border-green-400 hover:bg-green-50 data-[selected=true]:border-green-500 data-[selected=true]:bg-green-50 data-[selected=true]:text-green-700',
  },
};

const OTHER_OCCASION_CONFIG = {
  icon: <Tag className="h-4 w-4" />,
  color:
    'hover:border-zinc-400 hover:bg-zinc-50 data-[selected=true]:border-zinc-500 data-[selected=true]:bg-zinc-50 data-[selected=true]:text-zinc-700',
};

function configFor(value: string) {
  return value in OCCASION_CONFIG
    ? OCCASION_CONFIG[value as FeaturedOccasion]
    : OTHER_OCCASION_CONFIG;
}

interface OccasionChipsProps {
  selected: string | null;
  onSelect: (occasion: string) => void;
  extraOccasions?: readonly (string | null | undefined)[];
}

export function OccasionChips({ selected, onSelect, extraOccasions = [] }: OccasionChipsProps) {
  const occasions = useOccasionOptions([...extraOccasions, selected]);
  return (
    <div className="flex flex-wrap gap-2">
      {occasions.map((occasion) => {
        const config = configFor(occasion.value);
        return (
          <button
            key={occasion.value}
            type="button"
            onClick={() => onSelect(occasion.value)}
            data-selected={selected === occasion.value}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-full border-2 transition-all',
              'border-muted bg-background',
              config.color,
              'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary/50'
            )}
          >
            {config.icon}
            <span className="text-sm font-medium">{occasion.label}</span>
          </button>
        );
      })}
    </div>
  );
}
