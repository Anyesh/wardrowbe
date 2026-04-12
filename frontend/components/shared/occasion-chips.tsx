'use client';

import React from 'react';
import {
  Briefcase,
  Dumbbell,
  GlassWater,
  Heart,
  Shirt,
  TreePine,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { OCCASIONS } from '@/lib/types';

export const OCCASION_CONFIG: Record<
  string,
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

interface OccasionChipsProps {
  selected: string | null;
  onSelect: (occasion: string) => void;
}

export function OccasionChips({ selected, onSelect }: OccasionChipsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {OCCASIONS.map((occasion) => {
        const config = OCCASION_CONFIG[occasion.value];
        return (
          <button
            key={occasion.value}
            type="button"
            onClick={() => onSelect(occasion.value)}
            data-selected={selected === occasion.value}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-full border-2 transition-all',
              'border-muted bg-background',
              config?.color || 'hover:border-primary hover:bg-primary/5',
              'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary/50'
            )}
          >
            {config?.icon}
            <span className="text-sm font-medium">{occasion.label}</span>
          </button>
        );
      })}
    </div>
  );
}
