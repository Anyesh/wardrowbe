import { ApiError } from '@/lib/api';

export function isWornImmutableError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status !== 409) return false;
  const data = error.data as { detail?: { error_code?: string } } | undefined;
  return data?.detail?.error_code === 'OUTFIT_WORN_IMMUTABLE';
}
