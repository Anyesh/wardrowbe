import { CLOTHING_COLORS, COLOR_ALIASES } from '@/lib/generated/garment-vocabulary';

const SWATCHES = new Map<string, string>(CLOTHING_COLORS.map((c) => [c.value, c.hex]));

// Learned colour scores and rows written through the API can hold names outside the vocabulary
// (salmon, say), so they get a neutral swatch rather than none.
export const UNKNOWN_COLOR_SWATCH = 'hsl(var(--muted))';

export function colorSwatch(name: string): string {
  const key = name.trim().toLowerCase();
  return SWATCHES.get(key) ?? SWATCHES.get(COLOR_ALIASES[key] ?? '') ?? UNKNOWN_COLOR_SWATCH;
}
