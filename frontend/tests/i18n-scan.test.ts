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
})
