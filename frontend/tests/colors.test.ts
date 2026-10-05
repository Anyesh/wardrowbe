import { describe, expect, it } from 'vitest';
import { CLOTHING_COLORS } from '@/lib/types';
import { UNKNOWN_COLOR_SWATCH, colorSwatch } from '@/lib/colors';

const hexOf = (value: string) => CLOTHING_COLORS.find((c) => c.value === value)?.hex;

describe('colour swatches', () => {
  it.each(['light-blue', 'gold', 'silver'])('has a swatch for the tagger colour %s', (value) => {
    expect(hexOf(value)).toBeDefined();
    expect(colorSwatch(value)).toBe(hexOf(value));
  });

  it('resolves names outside the vocabulary through the alias table', () => {
    expect(colorSwatch('charcoal')).toBe(hexOf('gray'));
    expect(colorSwatch('Khaki')).toBe(hexOf('tan'));
    expect(colorSwatch('maroon')).toBe(hexOf('burgundy'));
    expect(hexOf('charcoal')).toBeUndefined();
  });

  it('falls back to a neutral swatch for unknown names', () => {
    expect(colorSwatch('salmon')).toBe(UNKNOWN_COLOR_SWATCH);
    expect(colorSwatch('')).toBe(UNKNOWN_COLOR_SWATCH);
  });
});
