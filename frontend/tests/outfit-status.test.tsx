import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { OutfitStatusFilter, OutfitStatusIcon } from '@/components/outfit-status'

// tests/setup.ts stubs next-intl to echo keys; these assertions need the real catalog.
vi.unmock('next-intl')

const history = JSON.parse(
  readFileSync(resolve(__dirname, '..', 'messages', 'en', 'history.json'), 'utf8'),
)

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="en" messages={{ history }} onError={() => {}}>
      {children}
    </NextIntlClientProvider>
  )
}

beforeAll(() => {
  // Radix Select calls these on open; jsdom does not implement them.
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

describe('OutfitStatusIcon', () => {
  it.each([
    ['pending', 'Pending'],
    ['sent', 'Sent'],
    ['viewed', 'Viewed'],
    ['accepted', 'Accepted'],
    ['rejected', 'Rejected'],
    ['skipped', 'Skipped'],
    ['expired', 'Expired'],
  ] as const)('labels %s as %s', (status, label) => {
    render(<OutfitStatusIcon status={status} />, { wrapper: Wrapper })
    expect(screen.getByRole('img', { name: label })).toBeInTheDocument()
  })
})

describe('OutfitStatusFilter', () => {
  it('offers every outfit status', () => {
    render(<OutfitStatusFilter value={undefined} onChange={vi.fn()} />, { wrapper: Wrapper })
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual([
      'All status',
      'Pending',
      'Sent',
      'Viewed',
      'Accepted',
      'Rejected',
      'Skipped',
      'Expired',
    ])
  })

  it('reports the chosen status and clears on "all"', () => {
    const onChange = vi.fn()
    const { rerender } = render(<OutfitStatusFilter value={undefined} onChange={onChange} />, {
      wrapper: Wrapper,
    })
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'Skipped' }))
    expect(onChange).toHaveBeenLastCalledWith('skipped')

    rerender(<OutfitStatusFilter value="skipped" onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    fireEvent.click(screen.getByRole('option', { name: 'All status' }))
    expect(onChange).toHaveBeenLastCalledWith(undefined)
  })
})
