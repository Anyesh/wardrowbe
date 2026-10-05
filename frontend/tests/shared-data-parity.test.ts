import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DEFAULT_LOCALE, LOCALE_METADATA, SUPPORTED_LOCALES } from '@/lib/i18n/locales';
import { RATING_MAX, RATING_MIN, TEMPERATURE_THRESHOLDS_CELSIUS } from '@/lib/generated/scales';
import { RATING_STARS } from '@/lib/rating';

const DATA_DIR = resolve(__dirname, '..', '..', 'backend', 'app', 'data');
const MESSAGES_DIR = resolve(__dirname, '..', 'messages');
const readData = (name: string) => JSON.parse(readFileSync(join(DATA_DIR, name), 'utf8'));

describe('locale codes', () => {
  const locales = readData('locales.json') as { default: string; supported: string[] };

  it('come from the backend locales file in picker order', () => {
    expect([...SUPPORTED_LOCALES]).toEqual(locales.supported);
    expect(DEFAULT_LOCALE).toBe(locales.default);
  });

  it('each have metadata and a messages directory', () => {
    const dirs = readdirSync(MESSAGES_DIR).filter((d) => statSync(join(MESSAGES_DIR, d)).isDirectory());
    expect(Object.keys(LOCALE_METADATA).sort()).toEqual([...SUPPORTED_LOCALES].sort());
    expect(dirs.sort()).toEqual([...SUPPORTED_LOCALES].sort());
  });
});

describe('scales', () => {
  const scales = readData('scales.json');

  it('come from the backend scales file', () => {
    expect(RATING_MIN).toBe(scales.rating.min);
    expect(RATING_MAX).toBe(scales.rating.max);
    expect(TEMPERATURE_THRESHOLDS_CELSIUS).toEqual(scales.temperature_thresholds_celsius);
  });

  it('render one star per rating step', () => {
    expect(RATING_STARS[0]).toBe(RATING_MIN);
    expect(RATING_STARS[RATING_STARS.length - 1]).toBe(RATING_MAX);
    expect(RATING_STARS).toHaveLength(RATING_MAX - RATING_MIN + 1);
  });
});
