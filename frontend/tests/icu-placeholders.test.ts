// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { placeholders } from '../scripts/icu-placeholders.mjs'

function names(value: string) {
  return Array.from(placeholders(value) as Set<string>).sort()
}

describe('ICU placeholders', () => {
  it.each([
    ['Hello {name}', ['name']],
    ['Worn {when, date, short} by {who}', ['when', 'who']],
    ['{count, plural, one {{count} day} other {{count} days}}', ['count']],
    ['{count, plural, one {# item from {owner}} other {# items from {owner}}}', ['count', 'owner']],
    ['{kind, select, top {Top} other {Piece {name}}}', ['kind', 'name']],
    ['{a} and {b, plural, other {x}} then {c}', ['a', 'b', 'c']],
  ])('finds the arguments in %s', (value, expected) => {
    expect(names(value)).toEqual(expected)
  })

  it('does not take a one-word plural branch for an argument', () => {
    expect(names('{count, plural, =0 {Filters} one {Filters, # active} other {Filters, # active}}')).toEqual([
      'count',
    ])
  })
})
