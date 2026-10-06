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

describe('normalizeColor', () => {
  it.each([
    ['Light Blue', 'light-blue'],
    ['light  blue', 'light-blue'],
    ['NAVY', 'navy'],
    ['charcoal', 'gray'],
    ['dark brown', 'brown'],
    ['salmon', null],
    ['', null],
  ])('reads %j as %j', (name, stored) => {
    expect(normalizeColor(name)).toBe(stored);
  });
});
