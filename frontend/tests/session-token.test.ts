import { describe, it, expect, beforeEach } from 'vitest'
import type { Session } from 'next-auth'
import { getAccessToken, setAccessToken } from '@/lib/api'
import { applySessionToken } from '@/lib/hooks/use-session-token'
import { sourceFiles } from './source-files'

const SESSION_TOKEN_MODULE = 'lib/hooks/use-session-token.ts'
// AuthProvider also clears the token when the session ends, which the per-hook sync must not do.
const ALLOWED = new Set([SESSION_TOKEN_MODULE, 'components/auth-provider.tsx'])

describe('applySessionToken', () => {
  beforeEach(() => setAccessToken('previous'))

  it('stores the session access token', () => {
    applySessionToken({ accessToken: 'abc', user: {}, expires: '' } as Session)
    expect(getAccessToken()).toBe('abc')
  })

  it('leaves the stored token alone when the session has none', () => {
    applySessionToken(null)
    applySessionToken({ user: {}, expires: '' } as Session)
    expect(getAccessToken()).toBe('previous')
  })
})

describe('session token sync has one definition', () => {
  it('no other module defines useSetTokenIfAvailable or copies its body', () => {
    const offenders = sourceFiles()
      .filter(({ path }) => !ALLOWED.has(path))
      .filter(
        ({ text }) =>
          /function useSetTokenIfAvailable/.test(text) ||
          /setAccessToken\(session\.accessToken/.test(text),
      )
      .map(({ path }) => path)
    expect(offenders).toEqual([])
  })
})
