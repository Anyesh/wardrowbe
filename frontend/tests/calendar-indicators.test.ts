import { describe, expect, it } from 'vitest';

import { buildCalendarIndicators } from '@/lib/outfits/calendar-indicators';
import type { Outfit, OutfitSource } from '@/lib/hooks/use-outfits';

function makeOutfit(
  source: OutfitSource,
  occasion: string,
  scheduled_for: string | null,
): Outfit {
  return {
    id: `${source}-${occasion}-${scheduled_for}`,
    occasion,
    scheduled_for,
    status: 'pending',
    source,
    name: null,
    replaces_outfit_id: null,
    cloned_from_outfit_id: null,
    reasoning: null,
    style_notes: null,
    season: null,
    formality: null,
    palette: null,
    notes: null,
    highlights: null,
    weather: null,
    items: [],
    feedback: null,
    family_ratings: null,
    family_rating_average: null,
    family_rating_count: null,
    created_at: '2026-07-30T00:00:00Z',
  };
}

describe('buildCalendarIndicators', () => {
  it('marks scheduled outfits on their day', () => {
    const map = buildCalendarIndicators([makeOutfit('scheduled', 'casual', '2026-07-30')]);
    expect(map.get('2026-07-30')).toEqual({ scheduled: true, onDemand: false });
  });

  it('treats on_demand, manual and external as the on-demand indicator', () => {
    const map = buildCalendarIndicators([
      makeOutfit('on_demand', 'casual', '2026-07-30'),
      makeOutfit('manual', 'office', '2026-07-31'),
      makeOutfit('external', 'formal', '2026-08-01'),
    ]);
    expect(map.get('2026-07-30')?.onDemand).toBe(true);
    expect(map.get('2026-07-31')?.onDemand).toBe(true);
    expect(map.get('2026-08-01')?.onDemand).toBe(true);
  });

  it('excludes externally-authored pairings', () => {
    const map = buildCalendarIndicators([makeOutfit('external', 'pairing', '2026-07-30')]);
    expect(map.has('2026-07-30')).toBe(false);
  });

  it('excludes internally-generated pairings', () => {
    const map = buildCalendarIndicators([makeOutfit('pairing', 'pairing', '2026-07-30')]);
    expect(map.has('2026-07-30')).toBe(false);
  });

  it('keeps a day marked when a pairing shares it with a real suggestion', () => {
    const map = buildCalendarIndicators([
      makeOutfit('external', 'pairing', '2026-07-30'),
      makeOutfit('external', 'casual', '2026-07-30'),
    ]);
    expect(map.get('2026-07-30')).toEqual({ scheduled: false, onDemand: true });
  });

  it('combines both indicators on the same day', () => {
    const map = buildCalendarIndicators([
      makeOutfit('scheduled', 'casual', '2026-07-30'),
      makeOutfit('external', 'office', '2026-07-30'),
    ]);
    expect(map.get('2026-07-30')).toEqual({ scheduled: true, onDemand: true });
  });

  it('skips lookbook entries with no date', () => {
    const map = buildCalendarIndicators([makeOutfit('manual', 'casual', null)]);
    expect(map.size).toBe(0);
  });
});
