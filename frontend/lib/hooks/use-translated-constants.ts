'use client';

import { useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import {
  CLOTHING_TYPES,
  CLOTHING_COLORS,
  OCCASIONS,
} from '@/lib/types';

/**
 * Returns clothing types with translated labels.
 * The `value` property is preserved for lookups and API calls.
 */
export function useClothingTypes() {
  const t = useTranslations('types.clothingTypes');
  const locale = useLocale();

  return useMemo(() => CLOTHING_TYPES.map((ct) => ({
    ...ct,
    label: t(ct.value),
  })), [t, locale]);
}

/**
 * Returns clothing colors with translated names.
 * The `value` and `hex` properties are preserved.
 */
export function useClothingColors() {
  const t = useTranslations('types.clothingColors');
  const locale = useLocale();

  return useMemo(() => CLOTHING_COLORS.map((cc) => ({
    ...cc,
    name: t(cc.value),
  })), [t, locale]);
}

/**
 * Returns occasions with translated labels.
 * The `value` property is preserved.
 */
export function useOccasions() {
  const t = useTranslations('types.occasions');
  const locale = useLocale();

  return useMemo(() => OCCASIONS.map((o) => ({
    ...o,
    label: t(o.value),
  })), [t, locale]);
}
