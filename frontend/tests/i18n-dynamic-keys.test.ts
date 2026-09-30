import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CLOTHING_COLORS, CLOTHING_TYPES, OCCASIONS } from '@/lib/types';
import { SUPPORTED_LOCALES } from '@/lib/i18n/locales';

// scripts/i18n-keys.mjs resolves t('literal') call sites, but several components build the key at
// runtime, e.g. t(`status.${status}`) or t(ct.value). Those are invisible to static analysis and
// render a raw key path for any value missing from the catalog, so they are asserted here instead.

const MESSAGES = resolve(__dirname, '..', 'messages');

function flatten(obj: Record<string, unknown>, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flatten(v as Record<string, unknown>, path));
    else out[path] = v;
  }
  return out;
}

function loadLocale(locale: string): Record<string, unknown> {
  const dir = join(MESSAGES, locale);
  const flat: Record<string, unknown> = {};
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const ns = file.slice(0, -5);
    for (const [k, v] of Object.entries(flatten(JSON.parse(readFileSync(join(dir, file), 'utf8'))))) {
      flat[`${ns}.${k}`] = v;
    }
  }
  return flat;
}

const en = loadLocale('en');

// Mirrors of module-private lists. Importing them would pull whole page components into jsdom, so
// they are duplicated here; if one of these lists changes at its source, this test must change too.
const OUTFIT_STATUSES = ['pending', 'sent', 'viewed', 'accepted', 'rejected', 'expired'] as const;
const NOTIFICATION_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;
const CALENDAR_WEEKDAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const;
const WARDROBE_SORTS = [
  'newestFirst', 'oldestFirst', 'recentlyWorn', 'leastRecentlyWorn',
  'mostWorn', 'leastWorn', 'nameAZ', 'nameZA',
] as const;
const BODY_FIELDS = ['height', 'weight', 'chest', 'waist', 'hips', 'inseam'] as const;
const SIZE_FIELDS = ['shirt_size', 'pants_size', 'dress_size', 'shoe_size'] as const;
const STYLE_VALUES = ['bold', 'casual', 'formal', 'minimalist', 'sporty'] as const;
const WEATHER_CONDITIONS = ['clear', 'cloudy', 'rain', 'snow'] as const;

const DYNAMIC_KEYS: Array<[string, readonly string[]]> = [
  ['constants.types', CLOTHING_TYPES.map((t) => t.value)],
  ['constants.colors', CLOTHING_COLORS.map((c) => c.value)],
  ['constants.occasions', OCCASIONS.map((o) => o.value)],
  ['constants.styles', STYLE_VALUES],
  ['constants.weatherConditions', WEATHER_CONDITIONS],
  ['history.status', OUTFIT_STATUSES],
  ['notifications.days', NOTIFICATION_DAYS],
  ['outfits.calendar.weekDays', CALENDAR_WEEKDAYS],
  ['wardrobe.sort', WARDROBE_SORTS],
  ['settings.body.fields', BODY_FIELDS],
  ['settings.body.sizePlaceholders', SIZE_FIELDS],
];

describe('runtime-built translation keys', () => {
  for (const [namespace, values] of DYNAMIC_KEYS) {
    it(`${namespace} covers all ${values.length} values`, () => {
      const missing = values.filter((v) => en[`${namespace}.${v}`] === undefined);
      expect(missing, `missing from messages/en: ${missing.map((m) => `${namespace}.${m}`).join(', ')}`).toEqual([]);
    });
  }
});

describe('locale catalogs', () => {
  const locales = readdirSync(MESSAGES).filter((d) => statSync(join(MESSAGES, d)).isDirectory());

  it('ships exactly the supported locales', () => {
    expect(locales.sort()).toEqual([...SUPPORTED_LOCALES].sort());
  });

  for (const locale of SUPPORTED_LOCALES) {
    if (locale === 'en') continue;
    it(`${locale} has the same key set as en`, () => {
      const target = loadLocale(locale);
      const missing = Object.keys(en).filter((k) => target[k] === undefined);
      const extra = Object.keys(target).filter((k) => en[k] === undefined);
      expect({ missing: missing.slice(0, 20), extra: extra.slice(0, 20) }).toEqual({ missing: [], extra: [] });
    });
  }
});
