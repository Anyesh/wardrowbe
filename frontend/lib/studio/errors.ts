import { ApiError } from '@/lib/api';

export function isWornImmutableError(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'OUTFIT_WORN_IMMUTABLE';
}
