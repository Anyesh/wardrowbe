import { canonicalItemOrder, slotsForType } from '@/lib/studio/canonical-order';

export interface MergeResult<T extends { id: string; type: string }> {
  merged: T[];
  skipped: Array<{ item: T; conflict: T }>;
}

export function mergeAiAssist<T extends { id: string; type: string }>(
  canvas: T[],
  aiItems: T[]
): MergeResult<T> {
  const slotHolders = new Map<string, T>(
    canvas.flatMap((item) => slotsForType(item.type).map((slot) => [slot, item] as const))
  );

  const canvasIds = new Set(canvas.map((c) => c.id));
  const merged: T[] = [...canvas];
  const skipped: Array<{ item: T; conflict: T }> = [];

  for (const item of aiItems) {
    if (canvasIds.has(item.id)) continue;
    const slots = slotsForType(item.type);
    const conflict = slots.map((slot) => slotHolders.get(slot)).find(Boolean);
    if (conflict) {
      skipped.push({ item, conflict });
      continue;
    }
    merged.push(item);
    slots.forEach((slot) => slotHolders.set(slot, item));
  }

  return { merged: canonicalItemOrder(merged), skipped };
}
