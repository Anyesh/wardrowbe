// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { scanSource } from '../scripts/i18n-scan.mjs'

function kinds(source: string) {
  return scanSource(source, 'component.tsx').map((f: { kind: string; value: string }) => [
    f.kind,
    f.value,
  ])
}

describe('i18n scan', () => {
  it.each(['aria-label', 'title', 'alt', 'placeholder'])(
    'flags a one-word literal in %s, which the reader hears or sees as is',
    (attr) => {
      expect(kinds(`const A = () => <span ${attr}="required">*</span>`)).toEqual([
        [`attr:${attr}`, 'required'],
      ])
    },
  )

  it('flags a literal wrapped in an expression or a plain template', () => {
    expect(kinds('const A = () => <img alt={"photo"} />')).toEqual([['attr:alt', 'photo']])
    expect(kinds('const A = () => <img alt={`photo`} />')).toEqual([['attr:alt', 'photo']])
  })

  it('flags the literal text of a template with substitutions', () => {
    expect(kinds('const A = ({ n }) => <img alt={`Photo of ${n}`} />')).toEqual([
      ['attr:alt', 'Photo of'],
    ])
  })

  it('leaves translated, symbolic and brand attribute values alone', () => {
    expect(
      kinds(`const A = ({ t }) => (
        <>
          <img alt={t('photo')} />
          <a title="https://example.com" />
          <span aria-label="Wardrowbe" />
          <span title="--" />
          <img alt={\`\${name}\`} />
        </>
      )`),
    ).toEqual([])
  })

  it('still treats identifier-like literals as non-copy outside the text attributes', () => {
    expect(kinds('const A = () => <div className="required" data-state="open" />')).toEqual([])
  })

  it.each([
    ['a toast', 'toast.error(error.message)', 'error.message'],
    ['a fallback chain', "const m = err instanceof Error ? err.message : t('failed')", 'err.message'],
    ['JSX', 'const A = () => <p>{fallbackError.message}</p>', 'fallbackError.message'],
    ['a state setter', 'setError(e.message)', 'e.message'],
    ['a query error', 'const A = () => <p>{query.error?.message}</p>', 'query.error?.message'],
    ['destructuring', 'const { message } = error', 'message'],
  ])('flags an error message reaching the user through %s', (_, source, value) => {
    expect(kinds(source)).toEqual([['error-message', value]])
  })

  it.each([
    ['logging', "console.error('failed', error.message)"],
    ['parsing', 'const match = error.message.match(LIMIT)'],
    ['a non-error value', 'toast.success(t(data.message))'],
    [
      'a development-only block',
      "const A = () => <>{process.env.NODE_ENV === 'development' && <pre>{error.message}</pre>}</>",
    ],
  ])('leaves an error message alone in %s', (_, source) => {
    expect(kinds(source)).toEqual([])
  })

  it('flags lib error text only when a toast shows it', () => {
    const found = (source: string) => scanSource(source, 'lib/upload.ts').map((f: { kind: string }) => f.kind)
    expect(found('const record = { error: error.message }')).toEqual([])
    expect(found('toast.error(error.message)')).toEqual(['error-message'])
  })
})
