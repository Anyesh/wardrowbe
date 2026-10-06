'use client';

import { useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  CLOTHING_TYPES,
  CLOTHING_COLORS,
  FEATURED_OCCASIONS,
} from '@/lib/types';

const STYLE_VALUES = ['bold', 'casual', 'formal', 'minimalist', 'sporty'] as const;
const WEATHER_CONDITION_VALUES = ['clear', 'cloudy', 'rain', 'snow'] as const;

export function useClothingTypes() {
  const t = useTranslations('constants.types');

  return useMemo(() => CLOTHING_TYPES.map((ct) => ({
    ...ct,
    label: t(ct.value),
  })), [t]);
}

export function useClothingColors() {
  const t = useTranslations('constants.colors');

  return useMemo(() => CLOTHING_COLORS.map((cc) => ({
    ...cc,
    name: t(cc.value),
  })), [t]);
}

export function useOccasions() {
  const t = useTranslations('constants.occasions');

  return useMemo(() => FEATURED_OCCASIONS.map((o) => ({
    ...o,
    label: t(o.value),
  })), [t]);
}

export function useStyles() {
  const t = useTranslations('constants.styles');

  return useMemo(() => STYLE_VALUES.map((value) => ({
    value,
    label: t(value),
  })), [t]);
}

export function useWeatherConditions() {
  const t = useTranslations('constants.weatherConditions');

  return useMemo(() => WEATHER_CONDITION_VALUES.map((value) => ({
    value,
    label: t(value),
  })), [t]);
}

type CatalogTranslator = ((key: string) => string) & { has: (key: string) => boolean };

// Subtypes, materials and formalities can hold values outside the catalog (free text, or rows
// tagged before the vocabulary changed), so an unknown value falls back to the raw value made
// readable ("slip-dress" -> "Slip dress") instead of a key path.
function useCatalogLabel(t: CatalogTranslator) {
  return useCallback((value: string) => {
    const key = value.toLowerCase();
    if (t.has(key)) return t(key);
    const spaced = value.replace(/[-_]+/g, ' ').trim();
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }, [t]);
}

export function useSubtypeLabel() {
  return useCatalogLabel(useTranslations('constants.subtypes'));
}

export function useMaterialLabel() {
  return useCatalogLabel(useTranslations('constants.materials'));
}

export function useFormalityLabel() {
  return useCatalogLabel(useTranslations('constants.formalities'));
}

export function useOccasionLabel() {
  return useCatalogLabel(useTranslations('constants.occasions'));
}

export function useColorLabel() {
  return useCatalogLabel(useTranslations('constants.colors'));
}

export function useRoleLabel() {
  return useCatalogLabel(useTranslations('constants.roles'));
}
