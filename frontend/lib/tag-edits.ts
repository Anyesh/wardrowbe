import { CLOTHING_SUBTYPES, type Item, type ItemTags } from '@/lib/types';

// The tags a person can set by hand. In a change set, null clears a tag and a key that is
// left out is untouched. Nothing here is ever sent as a whole tags object.
export interface TagChanges {
  pattern?: string | null;
  material?: string | null;
  formality?: string | null;
  fit?: string | null;
  style?: string[];
  season?: string[];
  colors?: string[];
  primary_color?: string | null;
}

// An item update where tags is a change set rather than a full tags object.
export type ItemEdits = Omit<Partial<Item>, 'tags'> & { tags?: TagChanges };

// What the tag editor is showing. The primary colour is not part of it: the edit form already
// has a primary colour field (with the eyedropper), so the editor only handles the colours after it.
export interface TagDraft {
  pattern: string | null;
  material: string | null;
  formality: string | null;
  fit: string | null;
  style: string[];
  season: string[];
  // Secondary, tertiary and anything after them.
  extraColors: string[];
}

const SINGLE_VALUE_KEYS = ['pattern', 'material', 'formality', 'fit'] as const;

export function primaryColorOf(tags: ItemTags): string | undefined {
  return tags.primary_color || tags.colors?.[0] || undefined;
}

// The item's primary colour as the edit form shows it: the column, which can be set while the
// tags are still empty or say something else.
export function primaryColorOfItem(item: Item | null | undefined): string | undefined {
  return item ? item.primary_color || primaryColorOf(item.tags) : undefined;
}

export function draftFromTags(tags: ItemTags, primary = primaryColorOf(tags)): TagDraft {
  return {
    pattern: tags.pattern ?? null,
    material: tags.material ?? null,
    formality: tags.formality ?? null,
    fit: tags.fit ?? null,
    style: [...(tags.style ?? [])],
    season: [...(tags.season ?? [])],
    extraColors: (tags.colors ?? []).filter((c) => c !== primary),
  };
}

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, i) => value === b[i]);
}

// The colours of an item, primary first, each colour once.
export function colorsFrom(primary: string | undefined, extraColors: readonly string[]): string[] {
  return Array.from(new Set([primary, ...extraColors].filter((c): c is string => !!c)));
}

// Only what actually differs from the item, so saving without touching a tag sends no tags at all.
// `primary` is the colour in the edit form and `currentPrimary` the one it started from. A new
// primary alone is not a tag change: it goes as the item's primary_color, and the server reorders
// the colour list it holds, so a list the AI wrote while the form was open is not overwritten.
export function diffTags(
  original: ItemTags,
  draft: TagDraft,
  primary: string | undefined,
  currentPrimary: string | undefined = primaryColorOf(original),
): TagChanges {
  const changes: TagChanges = {};

  for (const key of SINGLE_VALUE_KEYS) {
    if (draft[key] !== (original[key] ?? null)) changes[key] = draft[key];
  }
  if (!sameList(draft.style, original.style ?? [])) changes.style = draft.style;
  if (!sameList(draft.season, original.season ?? [])) changes.season = draft.season;

  const colors = colorsFrom(primary, draft.extraColors);
  const originalExtras = draftFromTags(original, currentPrimary).extraColors;
  if (!sameList(colors, colorsFrom(primary, originalExtras))) changes.colors = colors;

  return changes;
}

// The item as the server will return it after an edit, for the optimistic update. A tag set to
// null disappears; the tags that were not mentioned stay as they were.
export function applyItemEdits(item: Item, edits: ItemEdits): Item {
  const { tags: tagChanges, ...fields } = edits;
  const next = { ...item, ...fields } as Item;
  if (!tagChanges) return next;

  const tags: Record<string, unknown> = { ...item.tags };
  const columns = next as unknown as Record<string, unknown>;
  for (const [key, value] of Object.entries(tagChanges)) {
    if (value === null) {
      delete tags[key];
      columns[key] = undefined;
    } else {
      tags[key] = value;
      columns[key] = value;
    }
  }
  next.tags = tags as unknown as ItemTags;
  return next;
}

// Changing an item's type leaves behind a subtype that only made sense for the old one
// ("button-down" on a T-shirt turned into a blouse). Drop it when it belongs to some other type's
// list and not to the new type's; free text the app has no list for is kept.
export function subtypeAfterTypeChange(newType: string, subtype: string): string {
  const key = subtype.trim().toLowerCase().replace(/\s+/g, '-');
  if (!key) return subtype;
  if ((CLOTHING_SUBTYPES[newType] ?? []).includes(key)) return subtype;
  const belongsToAnotherType = Object.entries(CLOTHING_SUBTYPES).some(
    ([type, list]) => type !== newType && list.includes(key),
  );
  return belongsToAnotherType ? '' : subtype;
}
