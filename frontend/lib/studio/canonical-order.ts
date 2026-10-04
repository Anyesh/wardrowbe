import { ITEM_ROLE } from '@/lib/generated/garment-vocabulary';

export { ITEM_ROLE };

export const CANONICAL_ROLE_ORDER = [
  'full_body',
  'base_top',
  'mid_layer',
  'suit',
  'outer_layer',
  'bottom',
  'legwear',
  'footwear',
  'socks',
  'neckwear',
  'accessory',
] as const;

// A suit takes its own slot rather than outer_layer so an overcoat can still go over it.
const ROLE_SLOTS: Record<string, readonly string[]> = {
  full_body: ['base_top', 'bottom'],
  suit: ['bottom', 'suit'],
};

export function slotsForType(type: string): readonly string[] {
  const role = ITEM_ROLE[type];
  if (!role || role === 'accessory') return [];
  return ROLE_SLOTS[role] ?? [role];
}

const ROLE_SORT_INDEX: Record<string, number> = Object.fromEntries(
  CANONICAL_ROLE_ORDER.map((role, idx) => [role, idx])
);

export function canonicalItemOrder<T extends { id: string; type: string }>(
  items: T[]
): T[] {
  const originalPositions = new Map(items.map((item, idx) => [item.id, idx]));
  return [...items].sort((a, b) => {
    const roleA = ITEM_ROLE[a.type] ?? '';
    const roleB = ITEM_ROLE[b.type] ?? '';
    const idxA =
      ROLE_SORT_INDEX[roleA] ?? CANONICAL_ROLE_ORDER.length;
    const idxB =
      ROLE_SORT_INDEX[roleB] ?? CANONICAL_ROLE_ORDER.length;
    if (idxA !== idxB) return idxA - idxB;
    return (
      (originalPositions.get(a.id) ?? 0) -
      (originalPositions.get(b.id) ?? 0)
    );
  });
}
