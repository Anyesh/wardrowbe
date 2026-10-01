import { canonicalItemOrder, slotsForType } from '@/lib/studio/canonical-order';

export interface MergeResult<T extends { id: string; type: string }> {
  merged: T[];
  skipped: Array<{ item: T; reason: string }>;
}

export function mergeAiAssist<T extends { id: string; type: string }>(
  canvas: T[],
  aiItems: T[]
): MergeResult<T> {
  const existingSlots = new Set<string>(canvas.flatMap((item) => slotsForType(item.type)));

  const canvasIds = new Set(canvas.map((c) => c.id));
  const merged: T[] = [...canvas];
  const skipped: Array<{ item: T; reason: string }> = [];

  for (const item of aiItems) {
    if (canvasIds.has(item.id)) continue;
    const slots = slotsForType(item.type);
    const taken = slots.find((slot) => existingSlots.has(slot));
    if (taken) {
      skipped.push({ item, reason: `already have a ${taken.replace('_', ' ')}` });
      continue;
    }
    merged.push(item);
    slots.forEach((slot) => existingSlots.add(slot));
  }

  return { merged: canonicalItemOrder(merged), skipped };
}
