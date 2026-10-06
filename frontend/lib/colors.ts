import { CLOTHING_COLORS, COLOR_ALIASES } from '@/lib/generated/garment-vocabulary';

const SWATCHES = new Map<string, string>(CLOTHING_COLORS.map((c) => [c.value, c.hex]));

// Learned colour scores and rows written through the API can hold names outside the vocabulary
// (salmon, say), so they get a neutral swatch rather than none.
export const UNKNOWN_COLOR_SWATCH = 'hsl(var(--muted))';

// Mirrors normalize_color in backend/app/utils/garment_vocabulary.py, so that "Light Blue" reads as
// the stored "light-blue" on both sides.
export function normalizeColor(name: string): string | null {
  const key = name.trim().toLowerCase();
  for (const candidate of [key, key.replace(/\s+/g, '-')]) {
    if (SWATCHES.has(candidate)) return candidate;
    if (Object.hasOwn(COLOR_ALIASES, candidate)) return COLOR_ALIASES[candidate];
  }
  return null;
}

export function colorSwatch(name: string): string {
  const color = normalizeColor(name);
  return (color && SWATCHES.get(color)) ?? UNKNOWN_COLOR_SWATCH;
}
