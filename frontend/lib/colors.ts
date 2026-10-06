import { CLOTHING_COLORS, COLOR_ALIASES } from '@/lib/generated/garment-vocabulary';

const SWATCHES = new Map<string, string>(CLOTHING_COLORS.map((c) => [c.value, c.hex]));

// Learned colour scores and rows written through the API can hold names outside the vocabulary
// (salmon, say), so they get a neutral swatch rather than none.
export const UNKNOWN_COLOR_SWATCH = 'hsl(var(--muted))';

// Zero-width space, word joiner and BOM are dropped so that a name made only of them reads as blank
// rather than as an invisible colour; ZWJ and ZWNJ stay because they shape scripts and emoji.
const ZERO_WIDTH = /[\u200b\u2060\ufeff]/g;

// Unicode White_Space spelled out rather than \s because the backend and the colour migrations' SQL
// use this exact class, and \s differs between JavaScript, Python and Postgres.
const WHITESPACE_RUN = /[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g;

// Mirrors normalize_color in backend/app/utils/garment_vocabulary.py, so that "Light Blue" reads as
// the stored "light-blue" on both sides.
export function normalizeColor(name: string): string | null {
  const key = name
    .replace(ZERO_WIDTH, '')
    .replace(WHITESPACE_RUN, ' ')
    .replace(/^ | $/g, '')
    .toLowerCase();
  for (const candidate of [key, key.replaceAll(' ', '-')]) {
    if (SWATCHES.has(candidate)) return candidate;
    if (Object.hasOwn(COLOR_ALIASES, candidate)) return COLOR_ALIASES[candidate];
  }
  return null;
}

export function colorSwatch(name: string): string {
  const color = normalizeColor(name);
  return (color && SWATCHES.get(color)) ?? UNKNOWN_COLOR_SWATCH;
}
