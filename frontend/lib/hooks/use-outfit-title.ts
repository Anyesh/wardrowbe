'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type { Outfit } from '@/lib/hooks/use-outfits';
import { useOccasionLabel } from '@/lib/hooks/use-translated-constants';

type TitledOutfit = Pick<
  Outfit,
  'name' | 'replaces_outfit_id' | 'reasoning' | 'highlights' | 'occasion'
>;

export function useOutfitTitle() {
  const t = useTranslations('outfits.cards');
  const occasionLabel = useOccasionLabel();

  return useCallback(
    (outfit: TitledOutfit): string => {
      const occasion = occasionLabel(outfit.occasion);
      if (outfit.name) return outfit.name;
      if (outfit.replaces_outfit_id) return t('woreInsteadFallback', { occasion });
      if (outfit.reasoning) return outfit.reasoning;
      if (outfit.highlights && outfit.highlights.length > 0) return outfit.highlights[0];
      return t('outfitFallback', { occasion });
    },
    [t, occasionLabel],
  );
}
