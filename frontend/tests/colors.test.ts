import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { UNKNOWN_COLOR_SWATCH, colorSwatch, normalizeColor } from '@/lib/colors';

describe('colour swatches', () => {
  it.each([
    ['light-blue', '#9CBFE0'],
    ['gold', '#B08D3C'],
    ['silver', '#BFC1C2'],
    ['charcoal', '#808080'],
    ['Khaki', '#C9B896'],
    ['maroon', '#722F37'],
    ['Light Blue', '#9CBFE0'],
    [' NAVY ', '#1B2A4A'],
    ['Army Green', '#707B52'],
  ])('paints %s as %s', (name, hex) => {
    expect(colorSwatch(name)).toBe(hex);
  });

  it.each(['salmon', ''])('falls back to a neutral swatch for %j', (name) => {
    expect(colorSwatch(name)).toBe(UNKNOWN_COLOR_SWATCH);
  });
});

// The same cases drive normalize_color and canonical_color in the backend and the colour migrations'
// SQL, so the three implementations cannot drift apart.
const COLOR_NAME_CASES = JSON.parse(
  readFileSync(resolve(__dirname, '..', '..', 'backend', 'tests', 'fixtures', 'color_names.json'), 'utf8'),
) as Array<{ name: string; normalized: string | null }>;

describe('normalizeColor', () => {
  it.each(COLOR_NAME_CASES.map((c) => [c.name, c.normalized]))('reads %j as %j', (name, stored) => {
    expect(normalizeColor(name)).toBe(stored);
  });
});
