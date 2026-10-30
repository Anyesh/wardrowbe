'use client';

import { Footprints, Gem, Shirt } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCategoryLabel } from '@/lib/hooks/use-translated-constants';
import type { ItemCategory } from '@/lib/types';

// Written out in full so Tailwind can see every class; the colours come from the
// --category-* tokens in globals.css.
export const CATEGORY_STYLES: Record<ItemCategory, { chip: string; active: string; text: string }> = {
  clothing: {
    chip: 'border-category-clothing/25 bg-category-clothing/10 text-category-clothing',
    active: 'border-category-clothing bg-category-clothing/15 text-category-clothing',
    text: 'text-category-clothing',
  },
  footwear: {
    chip: 'border-category-footwear/25 bg-category-footwear/10 text-category-footwear',
    active: 'border-category-footwear bg-category-footwear/15 text-category-footwear',
    text: 'text-category-footwear',
  },
  accessories: {
    chip: 'border-category-accessories/25 bg-category-accessories/10 text-category-accessories',
    active: 'border-category-accessories bg-category-accessories/15 text-category-accessories',
    text: 'text-category-accessories',
  },
};

export const CATEGORY_ICONS: Record<ItemCategory, typeof Shirt> = {
  clothing: Shirt,
  footwear: Footprints,
  accessories: Gem,
};

export function CategoryBadge({ category, className }: { category: ItemCategory; className?: string }) {
  const label = useCategoryLabel();
  const Icon = CATEGORY_ICONS[category];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none',
        CATEGORY_STYLES[category].chip,
        className
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label(category)}
    </span>
  );
}
