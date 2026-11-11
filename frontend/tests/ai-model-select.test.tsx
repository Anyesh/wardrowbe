import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { AIModelSelect } from '@/components/ai-model-select'

// tests/setup.ts stubs next-intl to echo keys; these assertions need the real catalog.
vi.unmock('next-intl')

const messages = {
  settings: JSON.parse(readFileSync(resolve(__dirname, '..', 'messages', 'en', 'settings.json'), 'utf8')),
}

beforeAll(() => {
  // Radix Select calls these on open; jsdom does not implement them.
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

const VISION = ['Qwen/Qwen2.5-VL-7B-Instruct']
const TEXT = ['Qwen/Qwen2.5-7B-Instruct', 'llama-3.1-8b']

function renderSelect(props: Partial<Parameters<typeof AIModelSelect>[0]> = {}) {
  const onChange = vi.fn()
  render(
    <NextIntlClientProvider locale="en" messages={messages} onError={() => {}}>
      <AIModelSelect
        id="model"
        kind="vision"
        value={null}
        visionModels={VISION}
        textModels={TEXT}
        onChange={onChange}
        {...props}
      />
    </NextIntlClientProvider>,
  )
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
  return onChange
}

describe('AIModelSelect', () => {
  it('lists the models of the kind asked for first, after None', () => {
    renderSelect({ kind: 'text' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual([
      'None (do not use this server for it)',
      'Qwen/Qwen2.5-7B-Instruct',
      'llama-3.1-8b',
      'Qwen/Qwen2.5-VL-7B-Instruct',
    ])
    expect(within(screen.getByRole('group', { name: 'Other models' })).getAllByRole('option')).toHaveLength(2)
  })

  it('picks a model', () => {
    const onChange = renderSelect()
    fireEvent.click(screen.getByRole('option', { name: 'Qwen/Qwen2.5-VL-7B-Instruct' }))
    expect(onChange).toHaveBeenCalledWith('Qwen/Qwen2.5-VL-7B-Instruct')
  })

  it('clears the model with None', () => {
    const onChange = renderSelect({ value: 'llama-3.1-8b', kind: 'text' })
    fireEvent.click(screen.getByRole('option', { name: 'None (do not use this server for it)' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('keeps a saved model the server no longer lists', () => {
    renderSelect({ value: 'moondream' })
    expect(screen.getByRole('option', { name: 'moondream (not listed by the server)' })).toBeInTheDocument()
  })
})
