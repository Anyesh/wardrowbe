import { RATING_MAX, RATING_MIN } from '@/lib/generated/scales';

export const RATING_STARS: readonly number[] = Array.from(
  { length: RATING_MAX - RATING_MIN + 1 },
  (_, i) => RATING_MIN + i
);
