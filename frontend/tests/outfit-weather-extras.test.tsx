import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { OutfitWeatherExtras } from '@/components/shared/outfit-weather-extras'
import type { OutfitExtraItem } from '@/lib/types'

vi.unmock('next-intl')

function messages(locale: string, namespace: string) {
  return JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, `${namespace}.json`), 'utf8'),
  )
}

function wrapperFor(locale: string) {
  const all = Object.fromEntries(
    ['outfits', 'constants', 'common'].map((ns) => [ns, messages(locale, ns)]),
  )
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={all} onError={() => {}}>
        {children}
      </NextIntlClientProvider>
    )
  }
}

const extra = (overrides: Partial<OutfitExtraItem>): OutfitExtraItem => ({
  id: 'x1',
  type: 'cardigan',
  subtype: null,
  name: 'Grey cardigan',
  primary_color: 'grey',
  colors: ['grey'],
  image_path: null,
  thumbnail_path: null,
  image_url: null,
  thumbnail_url: 'https://example.test/thumb.jpg',
  ...overrides,
})

describe('OutfitWeatherExtras', () => {
  it('renders nothing when both extras are missing', () => {
    const { container } = render(<OutfitWeatherExtras ifCooler={null} ifWarmer={undefined} />, {
      wrapper: wrapperFor('en'),
    })
    expect(container).toBeEmptyDOMElement()
  })

  it('shows only the cooler row when only if_cooler is set', () => {
    render(<OutfitWeatherExtras ifCooler={extra({})} ifWarmer={null} />, {
      wrapper: wrapperFor('en'),
    })
    expect(screen.getByText('If it gets cooler: add Grey cardigan')).toBeInTheDocument()
    expect(screen.queryByText(/warms up/)).not.toBeInTheDocument()
  })

  it('shows only the warmer row when only if_warmer is set', () => {
    render(<OutfitWeatherExtras ifCooler={null} ifWarmer={extra({ id: 'x2', name: 'Denim jacket' })} />, {
      wrapper: wrapperFor('en'),
    })
    expect(screen.getByText('If it warms up: take off Denim jacket')).toBeInTheDocument()
    expect(screen.queryByText(/gets cooler/)).not.toBeInTheDocument()
  })

  it('shows both rows with a link to each item and falls back to the type label', () => {
    render(
      <OutfitWeatherExtras ifCooler={extra({ name: null })} ifWarmer={extra({ id: 'x2', name: 'Denim jacket' })} />,
      { wrapper: wrapperFor('en') },
    )
    expect(screen.getByText(/If it gets cooler: add \S+/)).toBeInTheDocument()
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/dashboard/wardrobe?item=x1',
      '/dashboard/wardrobe?item=x2',
    ])
  })

  it('translates the rows', () => {
    render(<OutfitWeatherExtras ifCooler={extra({})} ifWarmer={extra({ id: 'x2', name: 'Giacca' })} />, {
      wrapper: wrapperFor('it'),
    })
    expect(screen.getByText('Se si rinfresca: aggiungi Grey cardigan')).toBeInTheDocument()
    expect(screen.getByText('Se fa più caldo: togli Giacca')).toBeInTheDocument()
  })
})
