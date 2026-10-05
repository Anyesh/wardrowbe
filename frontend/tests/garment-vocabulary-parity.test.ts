import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import constants from '@/messages/en/constants.json';
import {
  CLOTHING_COLORS,
  COLOR_ALIASES,
  FORMALITY_VALUES,
  ITEM_ROLE,
  MATERIAL_VALUES,
  OCCASION_VALUES,
  ROLE_VALUES,
} from '@/lib/generated/garment-vocabulary';
import { SUPPORTED_LOCALES } from '@/lib/i18n/locales';
import { FEATURED_OCCASIONS, CLOTHING_TYPES } from '@/lib/types';

const VOCABULARY_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const vocabulary = JSON.parse(readFileSync(VOCABULARY_PATH, 'utf8')) as {
  roles: string[];
  types: Array<{ value: string; role: string }>;
  materials: string[];
  formality: string[];
  occasions: Array<{ value: string; formality?: string[] }>;
  colors: Array<{ value: string; hex: string }>;
  color_aliases: Record<string, string>;
};

const MESSAGES_PATH = resolve(__dirname, '..', 'messages');
const constantLabels = (locale: string, group: 'occasions' | 'colors'): Record<string, string> =>
  JSON.parse(readFileSync(resolve(MESSAGES_PATH, locale, 'constants.json'), 'utf8'))[group] ?? {};

const sorted = (values: Iterable<string>) => Array.from(values).sort();

describe('garment vocabulary', () => {
  it('generates the picker, roles and scales from the backend vocabulary file', () => {
    expect(sorted(CLOTHING_TYPES.map((type) => type.value))).toEqual(sorted(vocabulary.types.map((t) => t.value)));
    expect(ITEM_ROLE).toEqual(Object.fromEntries(vocabulary.types.map((t) => [t.value, t.role])));
    expect([...MATERIAL_VALUES]).toEqual(vocabulary.materials);
    expect([...FORMALITY_VALUES]).toEqual(vocabulary.formality);
    expect([...OCCASION_VALUES]).toEqual(vocabulary.occasions.map((o) => o.value));
    expect(CLOTHING_COLORS).toEqual(vocabulary.colors);
    expect(COLOR_ALIASES).toEqual(vocabulary.color_aliases);
    expect([...ROLE_VALUES]).toEqual(vocabulary.roles);
  });

  it('gives every stored colour a six-digit hex swatch', () => {
    expect(CLOTHING_COLORS.filter((c) => !/^#[0-9A-Fa-f]{6}$/.test(c.hex))).toEqual([]);
  });

  it.each(SUPPORTED_LOCALES)('labels exactly the stored colours in %s', (locale) => {
    expect(sorted(Object.keys(constantLabels(locale, 'colors')))).toEqual(sorted(CLOTHING_COLORS.map((c) => c.value)));
  });

  it('features only occasions the backend accepts', () => {
    const accepted = new Set<string>(OCCASION_VALUES);
    expect(FEATURED_OCCASIONS.filter((o) => !accepted.has(o.value))).toEqual([]);
  });

  it.each(SUPPORTED_LOCALES)('labels exactly the vocabulary occasions in %s', (locale) => {
    expect(sorted(Object.keys(constantLabels(locale, 'occasions')))).toEqual(sorted(OCCASION_VALUES));
  });

  it('has exactly one English label per type, material, formality and role', () => {
    expect(sorted(Object.keys(constants.types))).toEqual(sorted(vocabulary.types.map((t) => t.value)));
    expect(sorted(Object.keys(constants.materials))).toEqual(sorted(vocabulary.materials));
    expect(sorted(Object.keys(constants.formalities))).toEqual(sorted(vocabulary.formality));
    expect(sorted(Object.keys(constants.roles))).toEqual(sorted(vocabulary.roles));
  });
});
