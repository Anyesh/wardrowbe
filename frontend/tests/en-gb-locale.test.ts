// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { britishSpelling, buildCatalogs } from '../scripts/gen-en-gb.mjs'
import { resolveLocale } from '@/lib/i18n/locales'

describe('britishSpelling', () => {
  it('converts US spellings and keeps the source capitalisation', () => {
    expect(britishSpelling('Favorite Colors')).toBe('Favourite Colours')
    expect(britishSpelling('pick a color')).toBe('pick a colour')
    expect(britishSpelling('COLOR')).toBe('COLOUR')
    expect(britishSpelling('Re-analyze with AI')).toBe('Re-analyse with AI')
    expect(britishSpelling('3 analyzing')).toBe('3 analysing')
    expect(britishSpelling('Customize your personalized picks')).toBe('Customise your personalised picks')
  })

  it('leaves ICU argument names alone', () => {
    expect(britishSpelling('Heavy on {color} ({percent})')).toBe('Heavy on {color} ({percent})')
    expect(britishSpelling('{count, plural, one {# color} other {# colors}}')).toBe(
      '{count, plural, one {# colour} other {# colours}}',
    )
    expect(britishSpelling('{shade, select, gray {Gray tones} other {Other colors}}')).toBe(
      '{shade, select, gray {Grey tones} other {Other colours}}',
    )
  })

  it('only matches at the start of a word', () => {
    expect(britishSpelling('watercolors')).toBe('watercolors')
  })

  it('swaps whole clothing words but not words containing them', () => {
    expect(britishSpelling('Choose a shirt, pants, shoes')).toBe('Choose a shirt, trousers, shoes')
    expect(britishSpelling('Sneakers and a sweater')).toBe('Trainers and a jumper')
    expect(britishSpelling('sweatpants')).toBe('sweatpants')
  })
})

describe('en-GB catalogs', () => {
  const catalogs = buildCatalogs() as Record<string, Record<string, Record<string, string>>>

  it('uses British clothing words', () => {
    expect(catalogs.constants.types.pants).toBe('Trousers')
    expect(catalogs.constants.types.sweater).toBe('Jumper')
    expect(catalogs.constants.types.sneakers).toBe('Trainers')
    expect(catalogs.constants.seasons.fall).toBe('Autumn')
    expect(catalogs.constants.colors.gray).toBe('Grey')
  })

  it('keeps keys unchanged so lookups still resolve', () => {
    expect(Object.keys(catalogs.constants.types)).toContain('pants')
    expect(Object.keys(catalogs.wardrobe)).toContain('favorites')
  })
})

describe('resolveLocale for English variants', () => {
  it('picks en-GB for British browsers and en for other English', () => {
    expect(resolveLocale('en-GB')).toBe('en-GB')
    expect(resolveLocale('en-gb')).toBe('en-GB')
    expect(resolveLocale('en-US')).toBe('en')
    expect(resolveLocale('en')).toBe('en')
  })
})
