import { describe, expect, it } from 'vitest';
import {
  changedPurchaseFields,
  formatPurchaseDate,
  normalizePurchaseAmount,
  validatePurchaseFields,
} from '@/lib/purchase-fields';

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
    const previousTimezone = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      // This fails if the runner silently remains in UTC, so the assertion can
      // detect a regression to parsing ISO date-only strings as UTC.
      expect(new Date('2026-03-14').toLocaleDateString('en-US')).toBe('3/13/2026');
      expect(formatPurchaseDate('2026-03-14', 'en-US')).toBe('3/14/2026');
    } finally {
      if (previousTimezone === undefined) delete process.env.TZ;
      else process.env.TZ = previousTimezone;
    }
  });

  it('patches only changed purchase fields and sends null when cleared', () => {
    const original = { purchase_date: '2026-03-14', purchase_price: '124.50' };
    expect(changedPurchaseFields({ ...original, purchase_price: '124,50' }, original)).toEqual({});
    expect(changedPurchaseFields({ ...original, purchase_date: '' }, original))
      .toEqual({ purchase_date: null });
    expect(changedPurchaseFields({ ...original, purchase_price: '' }, original))
      .toEqual({ purchase_price: null });
    expect(changedPurchaseFields({ ...original, purchase_price: '125,25' }, original))
      .toEqual({ purchase_price: '125.25' });
  });
});
