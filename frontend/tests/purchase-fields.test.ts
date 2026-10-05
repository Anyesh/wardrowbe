import { describe, expect, it } from 'vitest';
import { formatPurchaseDate, normalizePurchaseAmount, validatePurchaseFields } from '@/lib/purchase-fields';

describe('purchase fields', () => {
  it('accepts optional fields and the full stored precision', () => {
    expect(validatePurchaseFields('', '')).toBeNull();
    expect(validatePurchaseFields('2026-02-28', '99999999.99')).toBeNull();
    expect(validatePurchaseFields('2024-02-29', '0')).toBeNull();
    expect(validatePurchaseFields('', '12,50')).toBeNull();
    expect(normalizePurchaseAmount(' 12,50 ')).toBe('12.50');
  });

  it('rejects impossible dates and amounts the database cannot store', () => {
    expect(validatePurchaseFields('2026-02-29', '10.00')).toBe('date');
    expect(validatePurchaseFields('2026-04-31', '10.00')).toBe('date');
    expect(validatePurchaseFields('', '-1')).toBe('amount');
    expect(validatePurchaseFields('', '12.345')).toBe('amount');
    expect(validatePurchaseFields('', '100000000')).toBe('amount');
    expect(validatePurchaseFields('', '1,234.56')).toBe('amount');
  });

  it('renders a date-only value without shifting it to the previous day', () => {
    const rendered = formatPurchaseDate('2026-03-14', 'en-US');
    expect(rendered).toBe('3/14/2026');
  });
});
