import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  UNKNOWN_COLOR_SWATCH,
  colorFamily,
  colorSwatch,
  isLightSwatch,
  normalizeColor,
  shadesOfFamily,
  withoutColorOverlaps,
} from '@/lib/colors';

describe('colour swatches', () => {
  it.each([
    ['light-blue', '#9CBFE0'],
    ['gold', '#B08D3C'],
    ['silver', '#BFC1C2'],
    ['charcoal', '#3C4142'],
    ['Khaki', '#F0E68C'],
    ['maroon', '#800000'],
    ['wine', '#722F37'],
    ['Sapphire', '#37527D'],
    ['blues', '#4A7DB8'],
    ['Light Blue', '#9CBFE0'],
    [' NAVY ', '#1B2A4A'],
    ['Army Green', '#707B52'],
  ])('paints %s as %s', (name, hex) => {
    expect(colorSwatch(name)).toBe(hex);
  });

  it.each(['chartreuse', ''])('falls back to a neutral swatch for %j', (name) => {
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

describe('colour families', () => {
  it.each([
    ['navy', 'blues'],
    ['Sapphire', 'blues'],
    ['dark grey', 'blacks-grays'],
    ['blues', 'blues'],
    ['chartreuse', null],
    ['', null],
  ])('puts %j in %j', (name, family) => {
    expect(colorFamily(name)).toBe(family);
  });

  it('lists the shades of a family, which include the original colours', () => {
    expect(shadesOfFamily('blues')).toEqual(expect.arrayContaining(['navy', 'blue', 'light-blue', 'sapphire']));
    expect(shadesOfFamily('blues')).not.toContain('teal');
  });

  it.each([
    ['#FAFAFA', true],
    ['#F0E68C', true],
    ['#1a1a1a', false],
    ['#4A7DB8', false],
  ])('reads %s as light: %s', (hex, light) => {
    expect(isLightSwatch(hex)).toBe(light);
  });
});

describe('withoutColorOverlaps', () => {
  it('drops shades of a family chosen on the other side', () => {
    expect(withoutColorOverlaps(['navy', 'sapphire', 'burgundy'], ['blues'])).toEqual(['burgundy']);
  });

  it('drops a family when one of its shades is chosen on the other side', () => {
    expect(withoutColorOverlaps(['blues', 'gray'], ['navy'])).toEqual(['gray']);
  });

  it('matches names outside the vocabulary only by themselves', () => {
    expect(withoutColorOverlaps(['chartreuse', 'gray'], ['Chartreuse'])).toEqual(['gray']);
  });
});
