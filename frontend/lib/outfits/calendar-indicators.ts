import type { Outfit, OutfitSource } from '@/lib/hooks/use-outfits';

const ON_DEMAND_SOURCES: OutfitSource[] = ['on_demand', 'manual', 'external'];

export interface DayIndicators {
  scheduled: boolean;
  onDemand: boolean;
}

// Pairings are anchored to a source item, not to a day; they carry scheduled_for only
// as a creation artifact, so they must not contribute a day indicator. Keyed on occasion
// because both internally-generated and externally-authored pairings have to be excluded
// and they do not share a source value.
export function buildCalendarIndicators(outfits: Outfit[]): Map<string, DayIndicators> {
  const map = new Map<string, DayIndicators>();

  outfits.forEach((outfit) => {
    const dateKey = outfit.scheduled_for;
    if (!dateKey || outfit.occasion === 'pairing') return;

    const entry = map.get(dateKey) ?? { scheduled: false, onDemand: false };
    if (outfit.source === 'scheduled') {
      entry.scheduled = true;
    } else if (ON_DEMAND_SOURCES.includes(outfit.source)) {
      entry.onDemand = true;
    }
    map.set(dateKey, entry);
  });

  return map;
}
