import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import constants from '@/messages/en/constants.json';
import { ITEM_ROLE } from '@/lib/studio/canonical-order';
import { CLOTHING_TYPES } from '@/lib/types';

const PROMPT_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'prompts', 'clothing_analysis.txt');

function promptOptions(heading: string): string[] {
  const match = readFileSync(PROMPT_PATH, 'utf8').match(new RegExp(`^${heading} \\([^)]*\\):\\n(.+)\\n`, 'm'));
  if (!match) throw new Error(`No ${heading} line found in ${PROMPT_PATH}`);
  return match[1].split(',').map((value) => value.trim());
}

const sorted = (values: Iterable<string>) => Array.from(values).sort();

describe('garment vocabulary', () => {
  it('offers the same types in the prompt, the picker and the outfit roles', () => {
    const fromPrompt = sorted(promptOptions('TYPE'));
    expect(sorted(CLOTHING_TYPES.map((type) => type.value))).toEqual(fromPrompt);
    expect(sorted(Object.keys(ITEM_ROLE))).toEqual(fromPrompt);
  });

  it('has exactly one English label per type, material, formality and role', () => {
    expect(sorted(Object.keys(constants.types))).toEqual(sorted(promptOptions('TYPE')));
    expect(sorted(Object.keys(constants.materials))).toEqual(sorted(promptOptions('MATERIAL')));
    expect(sorted(Object.keys(constants.formalities))).toEqual(sorted(promptOptions('FORMALITY')));
    expect(sorted(Object.keys(constants.roles))).toEqual(sorted(new Set(Object.values(ITEM_ROLE))));
  });
});
