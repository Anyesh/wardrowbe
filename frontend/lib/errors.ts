import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ApiError, NetworkError, type NetworkErrorKind } from '@/lib/api';
import { ERROR_CODE_PATTERN } from '@/lib/auth-errors';

export interface ErrorTranslator {
  (key: string, values?: Record<string, string | number>): string;
  has(key: string): boolean;
}

const NETWORK_CODES = { offline: 'NETWORK_OFFLINE', unreachable: 'NETWORK_CONNECT_FAILED' } as const;

export function networkErrorCode(kind: NetworkErrorKind): string {
  return NETWORK_CODES[kind];
}

// next-intl reports a formatting failure through onError and returns the key path, so that
// result counts as untranslated too.
export function translateCode(
  code: string | null | undefined,
  params: Record<string, string | number> | undefined,
  t: ErrorTranslator
): string | null {
  if (!code || !ERROR_CODE_PATTERN.test(code) || !t.has(code)) return null;
  const text = t(code, params);
  return text === `errors.${code}` || text === code ? null : text;
}

// Never returns an error's own message: server details and browser errors are English.
export function describeError(error: unknown, t: ErrorTranslator, fallback: string): string {
  if (error instanceof NetworkError) return translateCode(NETWORK_CODES[error.kind], {}, t) ?? fallback;
  if (error instanceof ApiError) return translateCode(error.code, error.params, t) ?? fallback;
  return fallback;
}

export function useDescribeError(): (error: unknown, fallback?: string) => string {
  const t = useTranslations('errors') as unknown as ErrorTranslator;
  return useCallback(
    (error: unknown, fallback?: string) => describeError(error, t, fallback ?? t('default')),
    [t]
  );
}
