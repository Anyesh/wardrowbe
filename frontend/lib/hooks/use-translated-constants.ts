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
// readable ("slip-dress" -> "Slip dress") instead of a key path. Keys are hyphenated because the
// backend sends some values with spaces ("partly cloudy"); this matches the cloud repo's termKey.
function useCatalogLabel(t: CatalogTranslator) {
  return useCallback((value: string) => {
    const key = value.trim().toLowerCase().replace(/\s+/g, '-');
    if (t.has(key)) return t(key);
    const spaced = value.replace(/[-_\s]+/g, ' ').trim();
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }, [t]);
}

export function useTypeLabel() {
  return useCatalogLabel(useTranslations('constants.types'));
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

export function useStyleLabel() {
  return useCatalogLabel(useTranslations('constants.styles'));
}

export function useColorLabel() {
  return useCatalogLabel(useTranslations('constants.colors'));
}

export function usePatternLabel() {
  return useCatalogLabel(useTranslations('constants.patterns'));
}

export function useFitLabel() {
  return useCatalogLabel(useTranslations('constants.fits'));
}

export function useSeasonLabel() {
  return useCatalogLabel(useTranslations('constants.seasons'));
}

export function useRoleLabel() {
  return useCatalogLabel(useTranslations('constants.roles'));
}

// The suggest page's weather override sends 'rainy', which the backend stores on the outfit as-is,
// while the forecast itself reports 'rain'.
const WEATHER_CONDITION_ALIASES: Record<string, string> = { rainy: 'rain' };

export function useWeatherConditionLabel() {
  const label = useCatalogLabel(useTranslations('constants.weatherConditions'));
  return useCallback(
    (value: string) => label(WEATHER_CONDITION_ALIASES[value.toLowerCase()] ?? value),
    [label]
  );
}

export interface OccasionOption {
  value: string;
  label: string;
}

// Pickers offer the featured occasions, but a stored value (a free-text default occasion, or an
// outfit created with another occasion) must stay visible and selectable instead of rendering as
// nothing selected, so each non-featured kept value is appended once.
export function useOccasionOptions(keep: readonly (string | null | undefined)[]): OccasionOption[] {
  const featured = useOccasions();
  const occasionLabel = useOccasionLabel();
  const options: OccasionOption[] = [...featured];
  for (const value of keep) {
    if (!value || options.some((o) => o.value === value)) continue;
    options.push({ value, label: occasionLabel(value) });
  }
  return options;
}
