// Generated from backend/app/data/scales.json by scripts/gen-shared-data.mjs.
// Do not edit by hand; run `npm run vocab:gen`.
export const RATING_MIN = 1;
export const RATING_MAX = 5;

export const TEMPERATURE_THRESHOLDS_CELSIUS = {
  cold: { min: -20, max: 30, default: 10 },
  hot: { min: 10, max: 45, default: 25 },
} as const;
