// Insights arrive from the API as {key, params}; params hold raw slugs and numbers that must be
// rendered in the user's language before they fill the message. Mirrors the cloud repo's
// packages/shared/src/insights.ts so that both products read the same API shape.
export type InsightParams = Record<string, string | number | string[]>;

export interface KeyedInsight {
  key: string;
  params: InsightParams;
}

export interface InsightLabelers {
  color: (slug: string) => string;
  style: (slug: string) => string;
  // Receives a percentage such as 45.5, not a fraction.
  percent: (value: number) => string;
  list: (items: string[]) => string;
}

export function localizeInsightParams(
  params: InsightParams,
  labelers: InsightLabelers,
): Record<string, string | number> {
  const localized: Record<string, string | number> = {};
  for (const [name, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      localized[name] = labelers.list(value.map((v) => (name === 'styles' ? labelers.style(v) : v)));
    } else if (name === 'color' && typeof value === 'string') {
      localized[name] = labelers.color(value);
    } else if (name === 'style' && typeof value === 'string') {
      localized[name] = labelers.style(value);
    } else if (name === 'percent' && typeof value === 'number') {
      localized[name] = labelers.percent(value);
    } else {
      localized[name] = value;
    }
  }
  return localized;
}
