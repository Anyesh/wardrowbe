import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import constants from '@/messages/en/constants.json';
import { FORMALITY_VALUES, ITEM_ROLE, MATERIAL_VALUES } from '@/lib/generated/garment-vocabulary';
import { CLOTHING_TYPES } from '@/lib/types';

const VOCABULARY_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const vocabulary = JSON.parse(readFileSync(VOCABULARY_PATH, 'utf8')) as {
  types: Array<{ value: string; role: string }>;
  materials: string[];
  formality: string[];
};

const sorted = (values: Iterable<string>) => Array.from(values).sort();

describe('garment vocabulary', () => {
  it('generates the picker, roles and scales from the backend vocabulary file', () => {
    expect(sorted(CLOTHING_TYPES.map((type) => type.value))).toEqual(sorted(vocabulary.types.map((t) => t.value)));
    expect(ITEM_ROLE).toEqual(Object.fromEntries(vocabulary.types.map((t) => [t.value, t.role])));
    expect([...MATERIAL_VALUES]).toEqual(vocabulary.materials);
    expect([...FORMALITY_VALUES]).toEqual(vocabulary.formality);
  });

  it('has exactly one English label per type, material, formality and role', () => {
    expect(sorted(Object.keys(constants.types))).toEqual(sorted(vocabulary.types.map((t) => t.value)));
    expect(sorted(Object.keys(constants.materials))).toEqual(sorted(vocabulary.materials));
    expect(sorted(Object.keys(constants.formalities))).toEqual(sorted(vocabulary.formality));
    expect(sorted(Object.keys(constants.roles))).toEqual(sorted(new Set(vocabulary.types.map((t) => t.role))));
  });
});
