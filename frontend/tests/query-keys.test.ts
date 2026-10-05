import { describe, it, expect } from 'vitest'
import { queryKeys } from '@/lib/hooks/query-keys'
import { sourceFiles } from './source-files'

const FACTORY = 'lib/hooks/query-keys.ts'

describe('queryKeys equal the literal keys they replaced', () => {
  const filters = { type: 'shirt' }
  const outfitFilters = { status: 'accepted' as const }

  it.each([
    ['authConfig', queryKeys.authConfig, ['auth-config']],
    ['authUser', queryKeys.authUser, ['auth-user']],
    ['userProfile', queryKeys.userProfile, ['user-profile']],
    ['features', queryKeys.features, ['features']],
    ['weather', queryKeys.weather, ['weather']],
    ['preferences', queryKeys.preferences, ['preferences']],
    ['family', queryKeys.family, ['family']],
    ['items.all', queryKeys.items.all, ['items']],
    ['items.list', queryKeys.items.list(filters, 2, 40), ['items', filters, 2, 40]],
    ['item', queryKeys.item('i1'), ['item', 'i1']],
    ['itemTypes', queryKeys.itemTypes, ['item-types']],
    ['colorDistribution', queryKeys.colorDistribution, ['color-distribution']],
    ['taggingProgress', queryKeys.taggingProgress, ['tagging-progress']],
    ['washHistory', queryKeys.washHistory('i1'), ['wash-history', 'i1']],
    ['wearStats.item', queryKeys.wearStats.item('i1'), ['wear-stats', 'i1']],
    ['wearHistory.list', queryKeys.wearHistory.list('i1', 20), ['wear-history', 'i1', 20]],
    ['outfits.all', queryKeys.outfits.all, ['outfits']],
    ['outfits.list', queryKeys.outfits.list(outfitFilters, 1, 20), ['outfits', outfitFilters, 1, 20]],
    [
      'outfits.infinite',
      queryKeys.outfits.infinite(outfitFilters, 20),
      ['outfits', 'infinite', outfitFilters, 20],
    ],
    ['outfit', queryKeys.outfit('o1'), ['outfit', 'o1']],
    ['outfit (undefined id)', queryKeys.outfit(undefined), ['outfit', undefined]],
    ['calendarOutfits.all', queryKeys.calendarOutfits.all, ['calendarOutfits']],
    [
      'calendarOutfits.month',
      queryKeys.calendarOutfits.month(2026, 10, outfitFilters),
      ['calendarOutfits', 2026, 10, outfitFilters],
    ],
    ['pendingOutfits.all', queryKeys.pendingOutfits.all, ['pendingOutfits']],
    ['pendingOutfits.list', queryKeys.pendingOutfits.list(3), ['pendingOutfits', 3]],
    ['familyOutfits.all', queryKeys.familyOutfits.all, ['familyOutfits']],
    [
      'familyOutfits.list',
      queryKeys.familyOutfits.list('m1', 1, 20),
      ['familyOutfits', 'm1', 1, 20],
    ],
    ['familyRatings', queryKeys.familyRatings('o1'), ['familyRatings', 'o1']],
    ['analytics.all', queryKeys.analytics.all, ['analytics']],
    ['analytics.summary', queryKeys.analytics.summary(30), ['analytics', 30]],
    ['learning.all', queryKeys.learning.all, ['learning']],
    [
      'learning.itemPairs',
      queryKeys.learning.itemPairs('i1', 5),
      ['learning', 'item-pairs', 'i1', 5],
    ],
    ['pairings.all', queryKeys.pairings.all, ['pairings']],
    ['pairings.list', queryKeys.pairings.list(20, 'ai'), ['pairings', 'list', 20, 'ai']],
    [
      'pairings.list (no source)',
      queryKeys.pairings.list(20, undefined),
      ['pairings', 'list', 20, undefined],
    ],
    ['pairings.forItem', queryKeys.pairings.forItem('i1'), ['pairings', 'item', 'i1']],
    [
      'pairings.forItemPage',
      queryKeys.pairings.forItemPage('i1', 1, 20),
      ['pairings', 'item', 'i1', 1, 20],
    ],
    ['notificationSettings', queryKeys.notificationSettings, ['notification-settings']],
    ['schedules', queryKeys.schedules, ['schedules']],
    ['notificationHistory', queryKeys.notificationHistory(20), ['notification-history', 20]],
  ])('%s', (_name, actual, expected) => {
    expect(actual).toStrictEqual(expected)
  })

  it('keeps detail keys out of the list prefixes the optimistic updaters rewrite', () => {
    expect(queryKeys.item('i1')[0]).not.toBe(queryKeys.items.all[0])
    expect(queryKeys.outfit('o1')[0]).not.toBe(queryKeys.outfits.all[0])
  })
})

describe('query keys come only from the factory', () => {
  it('no source file outside the factory writes a literal query key array', () => {
    const literalKey = /queryKey:\s*\[|(?:setQueryData|getQueryData)(?:<[^>]*>)?\(\s*\[/
    const offenders = sourceFiles()
      .filter(({ path }) => path !== FACTORY)
      .flatMap(({ path, text }) =>
        text
          .split('\n')
          .map((line, i) => ({ line, n: i + 1 }))
          .filter(({ line }) => literalKey.test(line))
          .map(({ n }) => `${path}:${n}`),
      )
    expect(offenders).toEqual([])
  })
})
