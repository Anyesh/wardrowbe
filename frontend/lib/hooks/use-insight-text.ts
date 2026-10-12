'use client';

import { useCallback, useMemo } from 'react';
import { useFormatter, useTranslations } from 'next-intl';
import { localizeInsightParams, type InsightLabelers, type KeyedInsight } from '@/lib/insights';
import { useColorLabel, useStyleLabel } from '@/lib/hooks/use-translated-constants';

function useInsightLabelers(): InsightLabelers {
  const colorLabel = useColorLabel();
  const styleLabel = useStyleLabel();
  const format = useFormatter();
  return useMemo(
    () => ({
      color: colorLabel,
      style: styleLabel,
      percent: (value) => format.number(value / 100, { style: 'percent', maximumFractionDigits: 1 }),
      list: (items) => format.list(items, { type: 'conjunction' }),
    }),
    [colorLabel, styleLabel, format],
  );
}

// Returns null for a key this build does not know, so callers can fall back to the English
// sentence the API still sends alongside.
export function useAnalyticsInsightText() {
  const t = useTranslations('analytics');
  const labelers = useInsightLabelers();
  return useCallback(
    (insight: KeyedInsight): string | null =>
      t.has(insight.key) ? t(insight.key, localizeInsightParams(insight.params, labelers)) : null,
    [t, labelers],
  );
}

export function useLearningInsightText() {
  const t = useTranslations('learning');
  const labelers = useInsightLabelers();
  return useCallback(
    (insight: KeyedInsight): { title: string; description: string } | null => {
      const title = `${insight.key}Title`;
      const description = `${insight.key}Description`;
      if (!t.has(title) || !t.has(description)) return null;
      const params = localizeInsightParams(insight.params, labelers);
      return { title: t(title, params), description: t(description, params) };
    },
    [t, labelers],
  );
}

const INSIGHT_CATEGORY_KEYS: Record<string, string> = {
  color: 'insightCategoryColor',
  style: 'insightCategoryStyle',
  overall: 'insightCategoryOverall',
  weather: 'insightCategoryWeather',
  occasion: 'insightCategoryOccasion',
};

export function useInsightCategoryLabel() {
  const t = useTranslations('learning');
  return useCallback(
    (category: string) => {
      const key = INSIGHT_CATEGORY_KEYS[category];
      return key ? t(key) : category;
    },
    [t],
  );
}

// Translated from insight_items, falling back per line to the English sentence for an API from
// before insight_items or a key this build lacks.
export function useAnalyticsInsightLines(
  data: { insights: string[]; insight_items?: KeyedInsight[] } | undefined,
): string[] {
  const insightText = useAnalyticsInsightText();
  return useMemo(() => {
    if (!data) return [];
    if (!data.insight_items) return data.insights;
    return data.insight_items
      .map((insight, i) => insightText(insight) ?? data.insights[i])
      .filter((line): line is string => Boolean(line));
  }, [data, insightText]);
}
