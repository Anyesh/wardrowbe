// @vitest-environment node
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { Account, User } from 'next-auth'
import type { JWT } from 'next-auth/jwt'
import { authOptions, authorizeForwardAuth } from '@/lib/auth'
import { FORWARD_AUTH_ACCOUNT_CONFLICT, FORWARD_AUTH_SERVER_ERROR } from '@/lib/auth-errors'

const SECRET = 'proxy-shared-secret-that-is-long-enough'

const SYNC_RESPONSE = {
  id: '6f1c2a4e-1111-2222-3333-444455556666',
  email: 'alice@example.com',
  display_name: 'Alice',
  is_new_user: true,
  onboarding_completed: false,
  access_token: 'backend-jwt',
}

function proxyHeaders(overrides: Record<string, string | undefined> = {}) {
  const headers: Record<string, string | undefined> = {
    'remote-user': 'alice',
    'remote-email': 'alice@example.com',
    'remote-name': 'Alice',
    'x-forward-auth-secret': SECRET,
    'x-forwarded-for': '203.0.113.7',
    'x-real-ip': '203.0.113.7',
    host: 'wardrobe.example.com',
    cookie: 'next-auth.csrf-token=abc',
    ...overrides,
  }
  return Object.fromEntries(Object.entries(headers).filter(([, v]) => v !== undefined))
}

function mockFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response)
  global.fetch = spy as unknown as typeof fetch
  return spy
}

describe('forward-auth authorize', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    vi.clearAllMocks()
    process.env.BACKEND_URL = 'http://backend:8000'
  })

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  it('syncs the proxy identity with the backend and keys the user by Remote-User', async () => {
    const spy = mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))

    const user = await authorizeForwardAuth(proxyHeaders())

    expect(spy).toHaveBeenCalledTimes(1)
    const [url, init] = spy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://backend:8000/api/v1/auth/sync')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      'remote-user': 'alice',
      'remote-email': 'alice@example.com',
      'remote-name': 'Alice',
      'x-forward-auth-secret': SECRET,
      'x-forwarded-for': '203.0.113.7',
      'x-real-ip': '203.0.113.7',
    })
    expect(init.headers).not.toHaveProperty('cookie')

    expect(user).toEqual({
      id: 'alice',
      email: 'alice@example.com',
      name: 'Alice',
      accessToken: 'backend-jwt',
      backendUserId: SYNC_RESPONSE.id,
      isNewUser: true,
      onboardingCompleted: false,
    })
  })

  it('keys the user by the UTF-8 Remote-User while relaying the raw header bytes', async () => {
    const spy = mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))
    const latin1 = (v: string) => String.fromCharCode(...Array.from(new TextEncoder().encode(v)))

    const user = await authorizeForwardAuth(
      proxyHeaders({ 'remote-user': latin1('josé'), 'remote-name': latin1('José Müller') })
    )

    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.headers).toMatchObject({ 'remote-user': latin1('josé') })
    expect(JSON.parse(init.body as string)).toMatchObject({
      external_id: 'josé',
      display_name: 'José Müller',
    })
    expect(user).toMatchObject({ id: 'josé' })
  })

  it('never returns the proxy secret', async () => {
    mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))

    const user = await authorizeForwardAuth(proxyHeaders())

    expect(JSON.stringify(user)).not.toContain(SECRET)
  })

  it('omits optional headers the proxy did not send', async () => {
    const spy = mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))

    await authorizeForwardAuth(
      proxyHeaders({ 'remote-name': undefined, 'x-forwarded-for': undefined, 'x-real-ip': undefined })
    )

    const init = spy.mock.calls[0][1] as RequestInit
    expect(Object.keys(init.headers as Record<string, string>).sort()).toEqual(
      ['content-type', 'remote-email', 'remote-user', 'x-forward-auth-secret'].sort()
    )
  })

  it.each([
    ['the secret', 'x-forward-auth-secret'],
    ['Remote-User', 'remote-user'],
    ['Remote-Email', 'remote-email'],
  ])('refuses without calling the backend when %s is missing', async (_label, header) => {
    const spy = mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))

    const user = await authorizeForwardAuth(proxyHeaders({ [header]: undefined }))

    expect(user).toBeNull()
    expect(spy).not.toHaveBeenCalled()
  })

  it.each([
    [401, 'Invalid forward-auth secret'],
    [400, 'Remote-Email is not a valid email address'],
  ])('refuses as a header problem when the backend answers %i', async (status, detail) => {
    mockFetch(new Response(JSON.stringify({ detail }), { status }))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(await authorizeForwardAuth(proxyHeaders())).toBeNull()
  })

  it('fails as an account conflict when the backend answers 409', async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: 'already in use by another account.' }), { status: 409 })
    )
    vi.spyOn(console, 'error').mockImplementation(() => {})

    await expect(authorizeForwardAuth(proxyHeaders())).rejects.toThrow(FORWARD_AUTH_ACCOUNT_CONFLICT)
  })

  it.each([500, 503])('fails as a server error when the backend answers %i', async (status) => {
    mockFetch(new Response(JSON.stringify({ detail: 'Internal Server Error' }), { status }))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    await expect(authorizeForwardAuth(proxyHeaders())).rejects.toThrow(FORWARD_AUTH_SERVER_ERROR)
  })

  it('fails as a server error when the backend is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed')) as unknown as typeof fetch
    vi.spyOn(console, 'error').mockImplementation(() => {})

    await expect(authorizeForwardAuth(proxyHeaders())).rejects.toThrow(FORWARD_AUTH_SERVER_ERROR)
  })

  it('is registered as a NextAuth provider that reads the request headers', async () => {
    // CredentialsProvider keeps the caller's id and authorize under `options`; NextAuth merges
    // them over the defaults when it initialises.
    type Configured = { options?: { id?: string; authorize?: (c: unknown, r: unknown) => unknown } }
    const provider = authOptions.providers.find(
      (p) => (p as Configured).options?.id === 'forward-auth'
    ) as Configured | undefined
    expect(provider).toBeDefined()

    mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))
    const user = await provider!.options!.authorize!({}, { headers: proxyHeaders(), method: 'POST' })
    expect(user).toMatchObject({ id: 'alice' })
  })
})

describe('jwt callback', () => {
  const jwt = authOptions.callbacks!.jwt!

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('copies the forward-auth sync result without calling the backend again', async () => {
    const spy = mockFetch(new Response('{}', { status: 200 }))
    const user = {
      id: 'alice',
      email: 'alice@example.com',
      name: 'Alice',
      accessToken: 'backend-jwt',
      backendUserId: SYNC_RESPONSE.id,
      isNewUser: true,
      onboardingCompleted: false,
    } as User
    const account = { provider: 'forward-auth', type: 'credentials', providerAccountId: 'alice' } as Account

    const token = (await jwt({
      token: { sub: 'alice', email: 'alice@example.com', name: 'Alice' } as JWT,
      user,
      account,
      trigger: 'signIn',
    })) as JWT

    expect(spy).not.toHaveBeenCalled()
    expect(token).toMatchObject({
      sub: 'alice',
      accessToken: 'backend-jwt',
      backendUserId: SYNC_RESPONSE.id,
      isNewUser: true,
      onboardingCompleted: false,
    })
    expect(JSON.stringify(token)).not.toContain(SECRET)
  })

  it('still syncs dev-credentials sign-ins with the backend', async () => {
    const spy = mockFetch(new Response(JSON.stringify(SYNC_RESPONSE), { status: 200 }))
    const account = { provider: 'dev-credentials', type: 'credentials', providerAccountId: 'dev' } as Account

    const token = (await jwt({
      token: { sub: 'dev' } as JWT,
      user: { id: 'dev', email: 'dev@example.com', name: 'Dev' } as User,
      account,
      trigger: 'signIn',
    })) as JWT

    expect(spy).toHaveBeenCalledTimes(1)
    expect(token.accessToken).toBe('backend-jwt')
  })
})
