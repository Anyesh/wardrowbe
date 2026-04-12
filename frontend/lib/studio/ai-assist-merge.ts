import { ITEM_ROLE, canonicalItemOrder } from '@/lib/studio/canonical-order';

export interface MergeResult<T extends { id: string; type: string }> {
  merged: T[];
  skipped: Array<{ item: T; reason: string }>;
}

export function mergeAiAssist<T extends { id: string; type: string }>(
  canvas: T[],
  aiItems: T[]
): MergeResult<T> {
  const existingSlots = new Set<string>();
  for (const item of canvas) {
    const role = ITEM_ROLE[item.type];
    if (role && role !== 'accessory') {
      existingSlots.add(role);
    }
  }

  const canvasIds = new Set(canvas.map((c) => c.id));
  const merged: T[] = [...canvas];
  const skipped: Array<{ item: T; reason: string }> = [];

  for (const item of aiItems) {
    if (canvasIds.has(item.id)) continue;
    const role = ITEM_ROLE[item.type];
    if (role && role !== 'accessory' && existingSlots.has(role)) {
      skipped.push({ item, reason: `already have a ${role.replace('_', ' ')}` });
      continue;
    }
    merged.push(item);
    if (role && role !== 'accessory') {
      existingSlots.add(role);
    }
  }

  return { merged: canonicalItemOrder(merged), skipped };
}
