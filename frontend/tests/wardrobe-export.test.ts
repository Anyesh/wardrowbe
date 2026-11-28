import { type AbstractIntlMessages, createTranslator } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import { type CatalogTranslator, catalogLabel } from '@/lib/hooks/use-translated-constants'
import {
  type CatalogueLabels,
  type ExportedItem,
  type ExportFileTranslator,
  renderCatalogue,
  type WardrobeExport,
} from '@/lib/wardrobe-export'
import deConstants from '@/messages/de/constants.json'
import deWardrobe from '@/messages/de/wardrobe.json'
import enWardrobe from '@/messages/en/wardrobe.json'
import jaConstants from '@/messages/ja/constants.json'
import jaWardrobe from '@/messages/ja/wardrobe.json'

vi.unmock('next-intl')

function labelsFor(
  locale: string,
  wardrobe: typeof enWardrobe,
  constants: AbstractIntlMessages,
): CatalogueLabels {
  const group = (namespace: string) =>
    catalogLabel(
      createTranslator({
        locale,
        messages: { constants },
        namespace: `constants.${namespace}`,
      }) as unknown as CatalogTranslator,
    )
  return {
    t: createTranslator({ locale, messages: { wardrobe }, namespace: 'wardrobe.exportFile' }),
    locale,
    type: group('types'),
    subtype: group('subtypes'),
    color: group('colors'),
    material: group('materials'),
    pattern: group('patterns'),
    formality: group('formalities'),
    style: group('styles'),
    season: group('seasons'),
    fit: group('fits'),
  }
}

const de = labelsFor('de', deWardrobe, deConstants)
const ja = labelsFor('ja', jaWardrobe, jaConstants)
const deQuoted = (name: string) =>
  String.fromCharCode(0x201e) + name + String.fromCharCode(0x201c)

function item(fields: Partial<ExportedItem>): ExportedItem {
  return {
    section: 'other',
    name: null,
    type: 'shirt',
    subtype: null,
    brand: null,
    primary_color: null,
    colors: [],
    pattern: null,
    material: null,
    style: [],
    formality: null,
    season: [],
    fit: null,
    description: null,
    notes: null,
    ...fields,
  }
}

function wardrobe(items: ExportedItem[]): WardrobeExport {
  return { exported_at: '2026-11-28T12:00:00', item_count: items.length, items }
}

const shirt = item({
  section: 'tops',
  type: 'shirt',
  subtype: 'oxford',
  brand: 'Uniqlo',
  primary_color: 'navy',
  colors: ['navy', 'white', 'red'],
  pattern: 'striped',
  material: 'cotton',
  style: ['casual', 'minimalist'],
  formality: 'casual',
  season: ['summer', 'spring'],
  fit: 'slim',
  description: 'Crisp oxford.',
  notes: 'Line one\n\n## Not a heading',
})
const jeans = item({
  section: 'bottoms',
  type: 'jeans',
  name: 'Old faithful',
  primary_color: 'navy',
  colors: ['navy'],
  pattern: 'solid',
  material: 'denim',
})
const sneakers = item({ section: 'footwear', type: 'sneakers', primary_color: 'white' })
const boots = item({ section: 'footwear', type: 'moon-boots', subtype: 'trail runner' })

describe('renderCatalogue', () => {
  it('writes the Markdown catalogue in the UI language', () => {
    expect(renderCatalogue(wardrobe([shirt, jeans, sneakers, boots]), 'markdown', de)).toBe(
      [
        '# Kleiderschrank',
        '',
        '_4 Stücke, exportiert am 28. November 2026_',
        '',
        '## Oberteile (1)',
        '- **[1] Oxford (Hemd) - von Uniqlo**',
        '  - Beschreibung: Crisp oxford.',
        '  - Details: Farbe: Marineblau (mit Weiß und Rot) | Material: Baumwolle | Muster: Gestreift | Formalität: Leger | Stil: Freizeit und Minimalistisch | Saison: Sommer und Frühling | Passform: Slim',
        '  - Notizen: Line one ## Not a heading',
        '',
        '## Unterteile (1)',
        `- **[2] ${deQuoted('Old faithful')} - Jeans**`,
        '  - Details: Farbe: Marineblau | Material: Denim',
        '',
        '## Schuhe & Socken (2)',
        '- **[3] Sneaker**',
        '  - Details: Farbe: Weiß',
        '- **[4] Trail runner (Moon boots)**',
        '',
      ].join('\n'),
    )
  })

  it('writes one line per item for plain text', () => {
    expect(renderCatalogue(wardrobe([shirt, jeans, boots]), 'text', de)).toBe(
      [
        '1. Oxford (Hemd) - von Uniqlo [Marineblau | Baumwolle]: Crisp oxford.',
        `2. ${deQuoted('Old faithful')} - Jeans [Marineblau | Denim]`,
        '3. Trail runner (Moon boots)',
        '',
      ].join('\n'),
    )
  })

  it('uses the singular summary for one item', () => {
    expect(renderCatalogue(wardrobe([sneakers]), 'markdown', de)).toContain(
      '_1 Stück, exportiert am 28. November 2026_',
    )
  })

  it('renders an empty export as a zero summary with no sections', () => {
    expect(renderCatalogue(wardrobe([]), 'markdown', de)).toBe(
      '# Kleiderschrank\n\n_0 Stücke, exportiert am 28. November 2026_\n',
    )
    expect(renderCatalogue(wardrobe([]), 'text', de)).toBe('')
  })

  it('follows the locale for punctuation, quotes and list separators', () => {
    const named = item({ ...shirt, name: 'お気に入り', brand: null, notes: null })
    const markdown = renderCatalogue(wardrobe([named]), 'markdown', ja)

    expect(markdown).toContain('_1点、2026年11月28日にエクスポート_')
    expect(markdown).toContain('## トップス（1）')
    expect(markdown).toContain('**[1] 「お気に入り」 - オックスフォード（シャツ）**')
    expect(markdown).toContain('色：ネイビー（白、赤を含む）')
    expect(markdown).toContain('季節：夏、春')
  })

  it('titles every backend section id', () => {
    const sections = [
      'tops',
      'bottoms',
      'full_body',
      'outerwear',
      'footwear',
      'accessories',
      'other',
    ] as const
    const markdown = renderCatalogue(
      wardrobe(sections.map((section) => item({ section }))),
      'markdown',
      de,
    )
    expect(markdown.match(/^## /gm)).toHaveLength(7)
    expect(markdown).toContain('## Einteiler & Anzüge (1)')
    expect(markdown).toContain('## Sonstiges (1)')
  })
})

describe('export file translator type', () => {
  it('rejects keys outside wardrobe.exportFile', () => {
    const t: ExportFileTranslator = createTranslator({
      locale: 'en',
      messages: { wardrobe: enWardrobe },
      namespace: 'wardrobe.exportFile',
    })

    expect(t('title')).toBe(enWardrobe.exportFile.title)

    // @ts-expect-error a key outside wardrobe.exportFile must not type-check
    const wrongKey = () => t('formats.skill.name')
    expect(typeof wrongKey).toBe('function')
  })
})
