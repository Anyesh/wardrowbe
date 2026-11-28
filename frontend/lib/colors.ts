import { CLOTHING_COLORS, COLOR_ALIASES, COLOR_FAMILIES } from '@/lib/generated/garment-vocabulary';

const SWATCHES = new Map<string, string>(CLOTHING_COLORS.map((c) => [c.value, c.hex]));
const FAMILY_SWATCHES = new Map<string, string>(COLOR_FAMILIES.map((f) => [f.value, f.hex]));
const FAMILY_OF = new Map<string, string>(CLOTHING_COLORS.map((c) => [c.value, c.family]));

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
function colorKey(name: string): string {
  return name
    .replace(ZERO_WIDTH, '')
    .replace(WHITESPACE_RUN, ' ')
    .replace(/^ | $/g, '')
    .toLowerCase();
}

export function normalizeColor(name: string): string | null {
  const key = colorKey(name);
  for (const candidate of [key, key.replaceAll(' ', '-')]) {
    if (SWATCHES.has(candidate)) return candidate;
    if (Object.hasOwn(COLOR_ALIASES, candidate)) return COLOR_ALIASES[candidate];
  }
  return null;
}

// Mirrors color_family in the backend: the family of a shade or alias, or a family name itself.
// Preferences and the colour analytics are stated per family, items per shade.
export function colorFamily(name: string): string | null {
  const key = colorKey(name);
  for (const candidate of [key, key.replaceAll(' ', '-')]) {
    if (FAMILY_SWATCHES.has(candidate)) return candidate;
  }
  const color = normalizeColor(name);
  return (color && FAMILY_OF.get(color)) ?? null;
}

// Mirrors the backend's overlap stripping: scoring matches a colour by name or family, so
// "navy" kept as a favourite would fight "blues" chosen to avoid. Drops from `colors` every
// colour that shares a name or family with one of `winners`.
export function withoutColorOverlaps(colors: string[], winners: string[]): string[] {
  const keys = (name: string) => [colorKey(name), colorFamily(name)].filter(Boolean);
  const taken = new Set(winners.flatMap(keys));
  return colors.filter((c) => !keys(c).some((key) => taken.has(key)));
}

export function isColorFamily(name: string): boolean {
  return FAMILY_SWATCHES.has(name);
}

export function shadesOfFamily(family: string): string[] {
  return CLOTHING_COLORS.filter((c) => c.family === family).map((c) => c.value);
}

export function colorSwatch(name: string): string {
  if (FAMILY_SWATCHES.has(name)) return FAMILY_SWATCHES.get(name)!;
  const color = normalizeColor(name);
  return (color && SWATCHES.get(color)) ?? UNKNOWN_COLOR_SWATCH;
}

// Whether a check mark or label drawn on this swatch should be dark, by perceived luminance.
export function isLightSwatch(hex: string): boolean {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) return false;
  const [r, g, b] = match.slice(1).map((part) => parseInt(part, 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 160;
}
