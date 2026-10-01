import { describe, it, expect } from 'vitest';

import { canonicalItemOrder, ITEM_ROLE } from '@/lib/studio/canonical-order';
import { mergeAiAssist } from '@/lib/studio/ai-assist-merge';
import { computeWarnings } from '@/lib/studio/warnings';
import type { StudioItem } from '@/lib/studio/editor-state';

function makeItem(id: string, type: string): StudioItem {
  return { id, type, name: `${type} item`, thumbnail_url: null, image_url: null, primary_color: null };
}

const t = (key: string) => key;

describe('suit role', () => {
  it('has its own role', () => {
    expect(ITEM_ROLE.suit).toBe('suit');
  });

  it('sorts after mid layers and before footwear', () => {
    const items = [makeItem('1', 'sneakers'), makeItem('2', 'suit'), makeItem('3', 'shirt')];
    expect(canonicalItemOrder(items).map((i) => i.type)).toEqual(['shirt', 'suit', 'sneakers']);
  });
});

describe('mergeAiAssist with multi-slot items', () => {
  it('keeps a shirt under a suit already on the canvas', () => {
    const { merged, skipped } = mergeAiAssist([makeItem('1', 'suit')], [makeItem('2', 'shirt')]);
    expect(merged.map((i) => i.type)).toEqual(['shirt', 'suit']);
    expect(skipped).toHaveLength(0);
  });

  it('skips trousers when a suit is already on the canvas', () => {
    const { merged, skipped } = mergeAiAssist([makeItem('1', 'suit')], [makeItem('2', 'pants')]);
    expect(merged).toHaveLength(1);
    expect(skipped.map((s) => s.item.id)).toEqual(['2']);
  });

  it('skips a suit when the canvas already has trousers', () => {
    const { merged, skipped } = mergeAiAssist(
      [makeItem('1', 'shirt'), makeItem('2', 'jeans')],
      [makeItem('3', 'suit')]
    );
    expect(merged).toHaveLength(2);
    expect(skipped.map((s) => s.item.id)).toEqual(['3']);
  });

  it('skips a shirt when a dress is already on the canvas', () => {
    const { merged, skipped } = mergeAiAssist([makeItem('1', 'dress')], [makeItem('2', 'shirt')]);
    expect(merged).toHaveLength(1);
    expect(skipped[0].reason).toContain('base top');
  });
});

describe('computeWarnings', () => {
  it('does not ask for bottoms when a suit covers them', () => {
    const warnings = computeWarnings([makeItem('1', 'shirt'), makeItem('2', 'suit')], t);
    expect(warnings).not.toContain('warnings.noBottoms');
    expect(warnings).not.toContain('warnings.multipleBottoms');
  });

  it('warns when a suit is combined with trousers', () => {
    const warnings = computeWarnings([makeItem('1', 'suit'), makeItem('2', 'pants')], t);
    expect(warnings).toContain('warnings.multipleBottoms');
  });

  it('warns when a dress is combined with trousers', () => {
    const warnings = computeWarnings([makeItem('1', 'dress'), makeItem('2', 'jeans')], t);
    expect(warnings).toContain('warnings.multipleBottoms');
  });

  it('still asks for bottoms when only a shirt is present', () => {
    expect(computeWarnings([makeItem('1', 'shirt')], t)).toContain('warnings.noBottoms');
  });

  it('still asks for a top when only trousers are present', () => {
    expect(computeWarnings([makeItem('1', 'jeans')], t)).toContain('warnings.noTop');
  });
});
