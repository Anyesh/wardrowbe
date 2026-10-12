import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ApiError, NetworkError } from '@/lib/api';

export interface ErrorTranslator {
  (key: string, values?: Record<string, string | number>): string;
  has(key: string): boolean;
}

// Never returns an error's own message: server details and browser errors are English, so an
// error without a known code or kind falls back to the caller's translated text.
export function describeError(error: unknown, t: ErrorTranslator, fallback: string): string {
  if (error instanceof NetworkError) return t(`network.${error.kind}`);
  if (error instanceof ApiError && error.code && t.has(`codes.${error.code}`)) {
    return t(`codes.${error.code}`, error.params);
  }
  return fallback;
}

export function useDescribeError(): (error: unknown, fallback: string) => string {
  const t = useTranslations('errors') as unknown as ErrorTranslator;
  return useCallback((error: unknown, fallback: string) => describeError(error, t, fallback), [t]);
}
