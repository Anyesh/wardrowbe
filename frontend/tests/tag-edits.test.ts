// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  applyItemEdits,
  colorsFrom,
  diffTags,
  draftFromTags,
  primaryColorOf,
  primaryColorOfItem,
  subtypeAfterTypeChange,
} from '@/lib/tag-edits'
import type { Item, ItemTags } from '@/lib/types'

const tags: ItemTags = {
  colors: ['navy', 'white'],
  primary_color: 'navy',
  pattern: 'striped',
  material: 'cotton',
  formality: 'casual',
  fit: 'slim',
  style: ['preppy'],
  season: ['spring', 'summer'],
}

describe('draftFromTags', () => {
  it('copies the tags and lists the colours after the primary', () => {
    expect(draftFromTags(tags)).toEqual({
      pattern: 'striped',
      material: 'cotton',
      formality: 'casual',
      fit: 'slim',
      style: ['preppy'],
      season: ['spring', 'summer'],
      extraColors: ['white'],
    })
  })

  it('handles an item with no tags yet', () => {
    expect(draftFromTags({ colors: [], style: [], season: [] })).toEqual({
      pattern: null,
      material: null,
      formality: null,
      fit: null,
      style: [],
      season: [],
      extraColors: [],
    })
  })

  it('does not share its lists with the item', () => {
    const draft = draftFromTags(tags)
    draft.style.push('sporty')
    expect(tags.style).toEqual(['preppy'])
  })

  it('takes the first colour as the primary when none is recorded', () => {
    expect(primaryColorOf({ colors: ['red', 'blue'], style: [], season: [] })).toBe('red')
  })

  it('leaves out the primary it is given rather than the one in the tags', () => {
    expect(
      draftFromTags({ ...tags, colors: ['black', 'white'], primary_color: 'black' }, 'navy').extraColors,
    ).toEqual(['black', 'white'])
  })
})

describe('primaryColorOfItem', () => {
  it('prefers the primary colour column', () => {
    expect(primaryColorOfItem({ primary_color: 'navy', tags } as unknown as Item)).toBe('navy')
  })

  it('falls back to the tags when the column is empty', () => {
    const item = { primary_color: null, tags: { colors: ['red', 'blue'], style: [], season: [] } }
    expect(primaryColorOfItem(item as unknown as Item)).toBe('red')
  })

  it('copes with no item', () => {
    expect(primaryColorOfItem(null)).toBeUndefined()
  })
})

describe('colorsFrom', () => {
  it('puts the primary first and drops repeats', () => {
    expect(colorsFrom('navy', ['white', 'navy', 'white'])).toEqual(['navy', 'white'])
  })

  it('copes with no primary', () => {
    expect(colorsFrom(undefined, ['white'])).toEqual(['white'])
  })
})

describe('diffTags', () => {
  it('is empty when nothing was touched', () => {
    expect(diffTags(tags, draftFromTags(tags), 'navy')).toEqual({})
  })

  it('reports only the keys that changed', () => {
    const draft = { ...draftFromTags(tags), pattern: 'plaid', fit: 'relaxed' }
    expect(diffTags(tags, draft, 'navy')).toEqual({ pattern: 'plaid', fit: 'relaxed' })
  })

  it('uses null to clear a tag', () => {
    const draft = { ...draftFromTags(tags), material: null }
    expect(diffTags(tags, draft, 'navy')).toEqual({ material: null })
  })

  it('reports a changed list in full, including emptying it', () => {
    const draft = { ...draftFromTags(tags), style: ['preppy', 'classic'], season: [] as string[] }
    expect(diffTags(tags, draft, 'navy')).toEqual({ style: ['preppy', 'classic'], season: [] })
  })

  it('does not treat a style or season list in a different order as a change', () => {
    const draft = { ...draftFromTags(tags), season: ['summer', 'spring'] }
    expect(diffTags(tags, draft, 'navy')).toEqual({})
  })

  it('sends a changed season list in the order the editor shows it', () => {
    const draft = { ...draftFromTags(tags), season: ['summer', 'fall', 'spring'] }
    expect(diffTags(tags, draft, 'navy')).toEqual({ season: ['summer', 'fall', 'spring'] })
  })

  it('adds a secondary colour after the primary', () => {
    const base = { colors: ['navy'], primary_color: 'navy', style: [], season: [] }
    const draft = { ...draftFromTags(base), extraColors: ['white'] }
    expect(diffTags(base, draft, 'navy')).toEqual({ colors: ['navy', 'white'] })
  })

  it('removes a secondary colour', () => {
    const draft = { ...draftFromTags(tags), extraColors: [] as string[] }
    expect(diffTags(tags, draft, 'navy')).toEqual({ colors: ['navy'] })
  })

  it('leaves a primary-only change to the primary colour field', () => {
    // The server puts the new primary at the front of the list it holds when the save lands.
    expect(diffTags(tags, draftFromTags(tags), 'red')).toEqual({})
  })

  it('sends the whole list when the colours after the primary change', () => {
    const draft = { ...draftFromTags(tags), extraColors: ['white', 'red'] }
    expect(diffTags(tags, draft, 'black')).toEqual({ colors: ['black', 'white', 'red'] })
  })

  it('sends nothing for an item with no primary column whose tags hold the colours', () => {
    const base = { colors: ['red', 'blue'], style: [], season: [] }
    expect(diffTags(base, draftFromTags(base, 'red'), 'red', 'red')).toEqual({})
  })

  it('sends nothing when the primary column and the tags disagree', () => {
    const base = { colors: ['black', 'white'], primary_color: 'black', style: [], season: [] }
    expect(diffTags(base, draftFromTags(base, 'navy'), 'navy', 'navy')).toEqual({})
  })

  it('does not repeat a colour that became the primary', () => {
    const draft = { ...draftFromTags(tags), extraColors: ['navy', 'white'] }
    expect(diffTags(tags, draft, 'navy').colors).toBeUndefined()
  })

  it('keeps colours past the third', () => {
    const base = { colors: ['navy', 'white', 'red', 'gold'], primary_color: 'navy', style: [], season: [] }
    const draft = draftFromTags(base)
    draft.extraColors[0] = 'green'
    expect(diffTags(base, draft, 'navy').colors).toEqual(['navy', 'green', 'red', 'gold'])
  })

  it('sends nothing for an item whose primary colour is set but whose tags are empty', () => {
    const empty = { colors: [], style: [], season: [] }
    expect(diffTags(empty, draftFromTags(empty), 'navy', 'navy')).toEqual({})
  })
})

describe('applyItemEdits', () => {
  const item = {
    id: 'i1',
    type: 'shirt',
    name: 'Oxford',
    colors: ['navy', 'white'],
    primary_color: 'navy',
    pattern: 'striped',
    tags: { ...tags, size: 'M' },
  } as unknown as Item

  it('changes plain fields and leaves tags alone when none were edited', () => {
    const next = applyItemEdits(item, { name: 'Blue oxford' })
    expect(next.name).toBe('Blue oxford')
    expect(next.tags).toEqual(item.tags)
  })

  it('merges edited tags into the existing ones instead of replacing them', () => {
    const next = applyItemEdits(item, { tags: { fit: 'relaxed' } })
    expect(next.tags).toEqual({ ...item.tags, fit: 'relaxed' })
    expect(next.tags.size).toBe('M')
  })

  it('removes a cleared tag from the tags and the item', () => {
    const next = applyItemEdits(item, { tags: { pattern: null } })
    expect('pattern' in next.tags).toBe(false)
    expect((next as unknown as Record<string, unknown>).pattern).toBeUndefined()
  })

  it('mirrors edited colours onto the item', () => {
    const next = applyItemEdits(item, { tags: { colors: ['red'], primary_color: 'red' } })
    expect(next.colors).toEqual(['red'])
    expect(next.primary_color).toBe('red')
  })

  it('does not modify the item it was given', () => {
    const before = JSON.stringify(item)
    applyItemEdits(item, { name: 'x', tags: { pattern: null, style: ['a'] } })
    expect(JSON.stringify(item)).toBe(before)
  })
})

describe('subtypeAfterTypeChange', () => {
  it('keeps a subtype that belongs to the new type', () => {
    expect(subtypeAfterTypeChange('shirt', 'button-down')).toBe('button-down')
  })

  it('drops a subtype that belongs to a different type', () => {
    expect(subtypeAfterTypeChange('t-shirt', 'button-down')).toBe('')
    expect(subtypeAfterTypeChange('dress', 'button-down')).toBe('')
  })

  it('drops a subtype that names a type', () => {
    expect(subtypeAfterTypeChange('leggings', 'leggings')).toBe('')
    expect(subtypeAfterTypeChange('sneakers', 'heels')).toBe('')
    expect(subtypeAfterTypeChange('shoes', 'Flats')).toBe('')
  })

  it('keeps a word that is a subtype of both the old and the new type', () => {
    expect(subtypeAfterTypeChange('socks', 'ankle')).toBe('ankle')
    expect(subtypeAfterTypeChange('boots', 'ankle')).toBe('ankle')
    expect(subtypeAfterTypeChange('socks', 'dress')).toBe('dress')
  })

  it('keeps free text the app has no list for', () => {
    expect(subtypeAfterTypeChange('shirt', 'Italian collar')).toBe('Italian collar')
  })

  it('matches however the subtype is written', () => {
    expect(subtypeAfterTypeChange('t-shirt', ' Button Down ')).toBe('')
  })

  it('leaves an empty subtype alone', () => {
    expect(subtypeAfterTypeChange('shirt', '')).toBe('')
  })
})
