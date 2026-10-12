import { STYLE_SCORE } from '@/lib/generated/scales';
import type { StyleProfile } from '@/lib/types';

export const DEFAULT_STYLE_PROFILE: StyleProfile = {
  casual: STYLE_SCORE.default,
  formal: STYLE_SCORE.default,
  sporty: STYLE_SCORE.default,
  minimalist: STYLE_SCORE.default,
  bold: STYLE_SCORE.default,
};
