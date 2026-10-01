import { slotsForType } from '@/lib/studio/canonical-order';
import type { StudioItem } from '@/lib/studio/editor-state';

export function computeWarnings(items: StudioItem[], t: (key: string) => string): string[] {
  const warnings: string[] = [];
  const slotsPerItem = items.map((i) => slotsForType(i.type));
  const covered = new Set(slotsPerItem.flat());

  const hasTop = covered.has('base_top');
  const hasBottom = covered.has('bottom');
  const hasFootwear = covered.has('footwear');

  if (hasTop && !hasBottom) {
    warnings.push(t('warnings.noBottoms'));
  }
  if (hasBottom && !hasTop) {
    warnings.push(t('warnings.noTop'));
  }

  if (slotsPerItem.filter((slots) => slots.includes('bottom')).length > 1) {
    warnings.push(t('warnings.multipleBottoms'));
  }

  if (items.length >= 3 && !hasFootwear) {
    warnings.push(t('warnings.noFootwear'));
  }

  return warnings;
}
