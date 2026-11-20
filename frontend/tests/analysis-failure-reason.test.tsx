import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import { AnalysisFailureReason } from '@/components/analysis-failure-reason'

vi.unmock('next-intl')

const MESSAGES = resolve(__dirname, '..', 'messages')
const LOCALES = readdirSync(MESSAGES)

const errorsFor = (locale: string): Record<string, string> =>
  JSON.parse(readFileSync(resolve(MESSAGES, locale, 'errors.json'), 'utf8'))

const WORKER_CODES: [string, Record<string, number>][] = [
  ['AI_RESPONSE_EMPTY', { max_tokens: 4096 }],
  ['AI_PROVIDER_ERROR', {}],
  ['AI_RESPONSE_UNUSABLE', {}],
  ['AI_HTTP_ERROR', { status: 404 }],
  ['AI_TIMEOUT', {}],
  ['AI_UNREACHABLE', {}],
  ['ANALYSIS_TIMED_OUT', {}],
  ['IMAGE_FILE_MISSING', {}],
  ['AI_VISION_DISABLED', {}],
  ['AI_ANALYSIS_FAILED', {}],
]

function renderReason(locale: string, props: Parameters<typeof AnalysisFailureReason>[0]) {
  return render(
    <NextIntlClientProvider locale={locale} messages={{ errors: errorsFor(locale) }}>
      <div data-testid="host">
        <AnalysisFailureReason {...props} />
      </div>
    </NextIntlClientProvider>
  )
}

describe('AnalysisFailureReason', () => {
  it('covers all eight locales', () => {
    expect(LOCALES).toHaveLength(8)
  })

  describe.each(LOCALES)('%s', (locale) => {
    it.each(WORKER_CODES)('translates %s with its params', (code, params) => {
      renderReason(locale, { code, params })

      const text = screen.getByTestId('host').textContent ?? ''
      expect(text).not.toBe('')
      expect(text).not.toContain(code)
      expect(text).not.toContain('{')
      for (const value of Object.values(params)) {
        expect(text).toContain(String(value))
      }
    })
  })

  it('renders the English catalog text for a code', () => {
    renderReason('en', { code: 'AI_HTTP_ERROR', params: { status: 401 } })

    expect(screen.getByTestId('host')).toHaveTextContent(
      errorsFor('en').AI_HTTP_ERROR.replace('{status}', '401')
    )
  })

  it('offers the whole translated reason as a tooltip, since the card clamps it', () => {
    renderReason('en', { code: 'AI_PROVIDER_ERROR', params: {} })

    expect(screen.getByText(errorsFor('en').AI_PROVIDER_ERROR)).toHaveAttribute(
      'title',
      errorsFor('en').AI_PROVIDER_ERROR
    )
  })

  it('gives the fallback no tooltip', () => {
    renderReason('en', { code: null, params: null, fallback: 'No reason' })

    expect(screen.getByText('No reason')).not.toHaveAttribute('title')
  })

  it.each([
    ['a legacy failure with no code', null],
    ['a code the catalog does not know', 'SOMETHING_NEW'],
  ])('renders the fallback for %s', (_, code) => {
    renderReason('de', { code, params: null, fallback: 'Kein Grund angegeben.' })

    expect(screen.getByTestId('host')).toHaveTextContent(/^Kein Grund angegeben\.$/)
  })

  it('renders nothing without a code or a fallback', () => {
    renderReason('en', { code: null, params: null })

    expect(screen.getByTestId('host')).toBeEmptyDOMElement()
  })
})
