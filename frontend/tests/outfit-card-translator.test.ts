import { createTranslator } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import type { OutfitCardTranslator } from '@/components/outfits/outfit-card'
import outfits from '@/messages/en/outfits.json'

vi.unmock('next-intl')

// tsc type-checks this file, so the @ts-expect-error below fails the build if the outfit card's
// translator stops rejecting keys outside outfits.cards.
describe('outfit card translator type', () => {
  it('accepts keys from outfits.cards and rejects others', () => {
    const t: OutfitCardTranslator = createTranslator({
      locale: 'en',
      messages: { outfits },
      namespace: 'outfits.cards',
    })

    expect(t('lookbookTemplate')).toBe(outfits.cards.lookbookTemplate)

    // @ts-expect-error a key outside outfits.cards must not type-check
    const wrongKey = () => t('notACardKey')
    expect(typeof wrongKey).toBe('function')
  })
})
