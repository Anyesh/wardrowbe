export type PurchaseFieldError = 'date' | 'amount' | null;

export interface PurchaseFields {
  purchase_date: string;
  purchase_price: string;
}

export function changedPurchaseFields(current: PurchaseFields, original: PurchaseFields): {
  purchase_date?: string | null;
  purchase_price?: string | null;
} {
  const changes: { purchase_date?: string | null; purchase_price?: string | null } = {};
  if (current.purchase_date !== original.purchase_date) {
    changes.purchase_date = current.purchase_date || null;
  }
  const currentAmount = normalizePurchaseAmount(current.purchase_price);
  if (currentAmount !== normalizePurchaseAmount(original.purchase_price)) {
    changes.purchase_price = currentAmount || null;
  }
  return changes;
}

export function normalizePurchaseAmount(amount: string): string {
  // Accept either decimal separator, but do not accept grouping punctuation.
  return amount.trim().replace(',', '.');
}

// The database stores an ISO date and a NUMERIC(10, 2) amount.
export function validatePurchaseFields(date: string, amount: string): PurchaseFieldError {
  if (date) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return 'date';
    const parsed = new Date(`${date}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
      return 'date';
    }
  }

  const normalizedAmount = normalizePurchaseAmount(amount);
  if (normalizedAmount && (!/^\d+(?:\.\d{1,2})?$/.test(normalizedAmount) || Number(normalizedAmount) > 99999999.99)) {
    return 'amount';
  }
  return null;
}

export function formatPurchaseDate(date: string, locale?: string): string {
  // Parsing a date-only string as UTC can show the previous day west of UTC.
  return new Date(`${date}T00:00:00`).toLocaleDateString(locale);
}

export function formatPurchaseAmount(amount: string | number, locale?: string): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(amount));
}
