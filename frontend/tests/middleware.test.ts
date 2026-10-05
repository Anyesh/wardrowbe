// @vitest-environment node
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'
import { encode } from 'next-auth/jwt'
import { getMiddlewareMatchers } from 'next/dist/build/analysis/get-page-static-info'
import { middleware, config } from '@/middleware'

const SECRET = 'nextauth-test-secret'
const SESSION = 'next-auth.session-token'
const SECURE_SESSION = '__Secure-next-auth.session-token'

async function sessionFor(sub: string) {
  return encode({ token: { sub, accessToken: 'backend-jwt' }, secret: SECRET })
}

function request(path: string, init: { remoteUser?: string; cookies?: Record<string, string> } = {}) {
  const headers = new Headers()
  if (init.remoteUser) headers.set('remote-user', init.remoteUser)
  if (init.cookies) {
    headers.set(
      'cookie',
      Object.entries(init.cookies)
        .map(([k, v]) => `${k}=${v}`)
        .join('; ')
    )
  }
  return new NextRequest(new URL(path, 'http://wardrobe.example.com'), { headers })
}

function clearedCookies(response: Response) {
  return response.headers
    .getSetCookie()
    .filter((c) => /Max-Age=0/i.test(c) || /Expires=Thu, 01 Jan 1970/i.test(c))
    .map((c) => c.split('=')[0])
    .sort()
}

describe('forward-auth user-switch middleware', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    process.env.NEXTAUTH_SECRET = SECRET
    process.env.NEXTAUTH_URL = 'http://wardrobe.example.com'
  })

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  it('does nothing without a Remote-User header, so dev and OIDC sessions are untouched', async () => {
    const response = await middleware(
      request('/dashboard', { cookies: { [SESSION]: await sessionFor('dev-user') } })
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([])
  })

  it('lets the request through when the proxy user matches the session', async () => {
    const response = await middleware(
      request('/dashboard', { remoteUser: 'alice', cookies: { [SESSION]: await sessionFor('alice') } })
    )

    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([])
  })

  it('lets the request through when nobody is signed in yet', async () => {
    const response = await middleware(request('/dashboard', { remoteUser: 'alice' }))

    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('redirects a page to login and clears every session chunk when the proxy user changed', async () => {
    const token = await sessionFor('alice')
    const half = Math.ceil(token.length / 2)

    const response = await middleware(
      request('/dashboard/wardrobe?type=shirt', {
        remoteUser: 'bob',
        cookies: {
          [`${SESSION}.0`]: token.slice(0, half),
          [`${SESSION}.1`]: token.slice(half),
          'next-auth.csrf-token': 'keep-me',
        },
      })
    )

    expect(response.status).toBe(307)
    const location = new URL(response.headers.get('location')!)
    expect(location.pathname).toBe('/login')
    expect(location.searchParams.get('callbackUrl')).toBe('/dashboard/wardrobe?type=shirt')
    expect(clearedCookies(response)).toEqual([`${SESSION}.0`, `${SESSION}.1`])
  })

  it('answers API calls with 401 JSON when the proxy user changed', async () => {
    const response = await middleware(
      request('/api/v1/items', { remoteUser: 'bob', cookies: { [SESSION]: await sessionFor('alice') } })
    )

    expect(response.status).toBe(401)
    expect(response.headers.get('content-type')).toContain('application/json')
    expect(await response.json()).toHaveProperty('detail')
    expect(clearedCookies(response)).toEqual([SESSION])
  })

  it('reads and clears the __Secure- cookie when NEXTAUTH_URL is https', async () => {
    process.env.NEXTAUTH_URL = 'https://wardrobe.example.com'

    const response = await middleware(
      request('/dashboard', { remoteUser: 'bob', cookies: { [SECURE_SESSION]: await sessionFor('alice') } })
    )

    expect(response.status).toBe(307)
    const cleared = response.headers.getSetCookie().find((c) => c.startsWith(`${SECURE_SESSION}=`))
    expect(cleared).toMatch(/Secure/i)
    expect(cleared).toMatch(/Path=\//i)
  })
})

describe('middleware matcher', () => {
  const matchers = getMiddlewareMatchers(config.matcher, {} as never)
  const matches = (path: string) => matchers.some((m) => new RegExp(m.regexp).test(path))

  it.each(['/', '/dashboard', '/dashboard/wardrobe', '/onboarding', '/api/v1/items', '/api/v1/auth/config'])(
    'runs on %s',
    (path) => {
      expect(matches(path)).toBe(true)
    }
  )

  it.each([
    '/api/auth/session',
    '/api/auth/callback/forward-auth',
    '/login',
    '/auth/logout',
    '/_next/static/chunks/main.js',
    '/_next/image',
    '/favicon.ico',
  ])('skips %s', (path) => {
    expect(matches(path)).toBe(false)
  })
})
