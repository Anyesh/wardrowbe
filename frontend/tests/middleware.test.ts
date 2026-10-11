// @vitest-environment node
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { encode } from 'next-auth/jwt'
import { getMiddlewareMatchers } from 'next/dist/build/analysis/get-page-static-info'
import { middleware, config } from '@/middleware'

const SECRET = 'nextauth-test-secret'
const SESSION = 'next-auth.session-token'
const SECURE_SESSION = '__Secure-next-auth.session-token'
const PROXY_SECRET = 'proxy-shared-secret-that-is-long-enough'

async function sessionFor(proxyUser: string) {
  return encode({ token: { sub: proxyUser, proxyUser, accessToken: 'backend-jwt' }, secret: SECRET })
}

async function otherProviderSession(sub: string) {
  return encode({ token: { sub, accessToken: 'backend-jwt' }, secret: SECRET })
}

type RequestInit = {
  remoteUser?: string
  secret?: string
  authorization?: string
  cookies?: Record<string, string>
}

function request(path: string, init: RequestInit = {}) {
  const headers = new Headers()
  if (init.remoteUser) headers.set('remote-user', init.remoteUser)
  if (init.secret) headers.set('x-forward-auth-secret', init.secret)
  if (init.authorization) headers.set('authorization', init.authorization)
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
    process.env.FORWARD_AUTH_SECRET = PROXY_SECRET
  })

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  // Only a request carrying this deployment's forward-auth secret came through a forward-auth proxy.
  it.each([
    { name: 'with no proxy in front', remoteUser: undefined, secret: undefined },
    { name: 'behind a proxy that sends Remote-User without the secret', remoteUser: 'alice', secret: undefined },
    { name: 'behind a proxy whose secret is not this deployment\'s', remoteUser: 'alice', secret: 'stale' },
  ])('leaves an OIDC or dev session alone $name', async ({ remoteUser, secret }) => {
    const response = await middleware(
      request('/dashboard', { remoteUser, secret, cookies: { [SESSION]: await otherProviderSession('oidc-sub') } })
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([])
  })

  // A forward-auth session without the secret or its Remote-User reached the frontend past the
  // proxy, and an OIDC or dev session behind a forward-auth proxy was left by whoever used the
  // browser before.
  it.each([
    { name: 'a forward-auth session without Remote-User', remoteUser: undefined, secret: PROXY_SECRET, oidc: false },
    { name: 'a forward-auth session without the secret', remoteUser: 'alice', secret: undefined, oidc: false },
    { name: 'a forward-auth session with a forged secret', remoteUser: 'alice', secret: 'forged', oidc: false },
    { name: 'an OIDC or dev session behind a forward-auth proxy', remoteUser: 'bob', secret: PROXY_SECRET, oidc: true },
  ])('ends $name', async ({ remoteUser, secret, oidc }) => {
    const session = oidc ? await otherProviderSession('alice-oidc-sub') : await sessionFor('alice')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const page = await middleware(request('/dashboard', { remoteUser, secret, cookies: { [SESSION]: session } }))
    const sessionAction = await middleware(
      request('/api/auth/session', { remoteUser, secret, cookies: { [SESSION]: session } })
    )

    expect(page.status).toBe(307)
    expect(new URL(page.headers.get('location')!).pathname).toBe('/login')
    expect(clearedCookies(page)).toEqual([SESSION])
    expect(await sessionAction.json()).toEqual({})
    expect(clearedCookies(sessionAction)).toEqual([SESSION])
    // Repeated on every page load when only the frontend has the secret, which is how an operator
    // tells that misconfiguration from a previous user's session.
    expect(warn).toHaveBeenCalledTimes(oidc ? 2 : 0)
    warn.mockRestore()
  })

  it('treats a bearer header it cannot decode as no session', async () => {
    const response = await middleware(request('/dashboard', { remoteUser: 'alice', authorization: 'Bearer %' }))

    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('lets the request through when the proxy user matches the session', async () => {
    const response = await middleware(
      request('/dashboard', { remoteUser: 'alice', secret: PROXY_SECRET, cookies: { [SESSION]: await sessionFor('alice') } })
    )

    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([])
  })

  it('matches a non-ASCII proxy user that Node read as Latin-1', async () => {
    const latin1 = String.fromCharCode(...Array.from(new TextEncoder().encode('josé')))
    const response = await middleware(
      request('/dashboard', { remoteUser: latin1, secret: PROXY_SECRET, cookies: { [SESSION]: await sessionFor('josé') } })
    )

    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([])
  })

  it('lets the request through when nobody is signed in yet', async () => {
    const response = await middleware(request('/dashboard', { remoteUser: 'alice', secret: PROXY_SECRET }))

    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  // A session request that was in flight in another tab when the user logged out answers with a
  // fresh session cookie; landing on the logged-out page must not sign the browser back in.
  it.each([
    ['the proxy user it belongs to', { remoteUser: 'alice', secret: PROXY_SECRET }],
    ['no proxy', {}],
  ])('clears a session that came back after logout, with %s', async (_, init) => {
    const response = await middleware(
      request('/login?loggedOut=1', { ...init, cookies: { [SESSION]: await sessionFor('alice'), 'next-auth.csrf-token': 'keep-me' } })
    )

    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(clearedCookies(response)).toEqual([SESSION])
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

  // NextAuth takes the action from the first segment after /api/auth and decodes it.
  it.each(['/api/auth/session', '/api/auth/session/x', '/api/auth/%73ession'])(
    'answers %s with no session when the proxy user changed',
    async (path) => {
      const response = await middleware(
        request(path, { remoteUser: 'bob', cookies: { [SESSION]: await sessionFor('alice') } })
      )

      expect(response.status).toBe(200)
      expect(await response.json()).toEqual({})
      expect(clearedCookies(response)).toEqual([SESSION])
    }
  )

  it.each(['/api/auth/callback/forward-auth', '/api/auth/csrf', '/api/auth/sessions'])(
    'lets %s through so the new proxy user can sign in',
    async (path) => {
      const response = await middleware(
        request(path, { remoteUser: 'bob', cookies: { [SESSION]: await sessionFor('alice') } })
      )

      expect(response.headers.get('x-middleware-next')).toBe('1')
      expect(clearedCookies(response)).toEqual([])
    }
  )

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
  const matches = (path: string) => {
    const url = new URL(path, 'http://wardrobe.example.com')
    return matchers.some(
      (m) =>
        new RegExp(m.regexp).test(url.pathname) &&
        (m.has ?? []).every((h) => h.type === 'query' && url.searchParams.get(h.key) === h.value)
    )
  }

  it.each([
    '/',
    '/dashboard',
    '/dashboard/wardrobe',
    '/onboarding',
    '/api/auth/session',
    '/api/auth/session/x',
    '/api/auth/%73ession',
    '/login?loggedOut=1',
  ])(
    'runs on %s',
    (path) => {
      expect(matches(path)).toBe(true)
    }
  )

  // API calls are left to the backend's own check, because a matched request has its whole body
  // buffered before it is forwarded, uploads included.
  it.each([
    '/api/v1/items',
    '/api/v1/items/upload',
    '/api/v1/auth/config',
    '/login',
    '/login?callbackUrl=%2Fdashboard',
    '/auth/logout',
    '/_next/static/chunks/main.js',
    '/_next/image',
    '/favicon.ico',
    '/logo.svg',
    '/icon-192.png',
    '/manifest.json',
  ])('skips %s', (path) => {
    expect(matches(path)).toBe(false)
  })
})
