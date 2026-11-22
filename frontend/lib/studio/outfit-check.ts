import { canonicalItemOrder, slotsForType } from '@/lib/studio/canonical-order';
import type { StudioItem } from '@/lib/studio/editor-state';

export type OutfitCheckAction = 'replace' | 'add' | 'remove' | 'styling_tip';

export interface OutfitCheckItem {
  id: string;
  type: string;
  name: string | null;
  primary_color: string | null;
  image_url: string | null;
  thumbnail_url: string | null;
}

export interface OutfitCheckSuggestion {
  action: OutfitCheckAction;
  title: string;
  description: string;
  reason: string;
  target_item_id: string | null;
  replacement_item: OutfitCheckItem | null;
}

export interface OutfitCheckResult {
  rating: number;
  verdict: string;
  opinion: string;
  strengths: string[];
  improvements: string[];
  suggestions: OutfitCheckSuggestion[];
}

export interface OutfitCheckPayload {
  items: string[];
  destination: string;
  occasion: string;
}

// Whether the canvas still has what a suggestion acts on: a swap or removal of a piece the
// user already took off, or a piece that is already on the canvas, has nothing left to do.
export function canApplySuggestion(items: StudioItem[], suggestion: OutfitCheckSuggestion): boolean {
  const ids = new Set(items.map((i) => i.id));
  switch (suggestion.action) {
    case 'remove':
      return suggestion.target_item_id !== null && ids.has(suggestion.target_item_id);
    case 'replace':
      return (
        suggestion.target_item_id !== null &&
        ids.has(suggestion.target_item_id) &&
        suggestion.replacement_item !== null &&
        !ids.has(suggestion.replacement_item.id)
      );
    case 'add':
      return suggestion.replacement_item !== null && !ids.has(suggestion.replacement_item.id);
    default:
      return false;
  }
}

// Applies a suggestion the way the studio fills slots: the new piece takes the target's place
// and also displaces whatever else holds its slots, so swapping in a dress clears top and bottom.
export function applySuggestion(
  items: StudioItem[],
  suggestion: OutfitCheckSuggestion
): StudioItem[] {
  if (!canApplySuggestion(items, suggestion)) return items;
  const kept = items.filter((i) => i.id !== suggestion.target_item_id);
  const incoming = suggestion.replacement_item;
  if (suggestion.action === 'remove' || !incoming) return kept;

  const slots = new Set(slotsForType(incoming.type));
  const unblocked = kept.filter((i) => !slotsForType(i.type).some((slot) => slots.has(slot)));
  return canonicalItemOrder([
    ...unblocked,
    {
      id: incoming.id,
      type: incoming.type,
      name: incoming.name,
      primary_color: incoming.primary_color,
      image_url: incoming.image_url,
      thumbnail_url: incoming.thumbnail_url,
    },
  ]);
}
