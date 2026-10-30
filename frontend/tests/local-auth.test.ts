// @vitest-environment node
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Account, User } from 'next-auth'
import type { JWT } from 'next-auth/jwt'
import { authOptions, authorizePasskey, authorizePassword } from '@/lib/auth'
import {
  LOCAL_INVALID_CREDENTIALS,
  LOCAL_SERVER_ERROR,
  LOCAL_TOO_MANY_ATTEMPTS,
  PASSKEY_REJECTED,
} from '@/lib/auth-errors'

const SIGNED_IN = {
  id: '6f1c2a4e-1111-2222-3333-444455556666',
  email: 'alice@example.com',
  display_name: 'Alice',
  is_new_user: false,
  onboarding_completed: true,
  access_token: 'backend-jwt',
}

function mockFetch(response: Response | Error) {
  const spy =
    response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response)
  global.fetch = spy as unknown as typeof fetch
  return spy
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

describe('password sign-in', () => {
  beforeEach(() => {
    process.env.BACKEND_URL = 'http://backend:8000'
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('exchanges the credentials for the backend session token', async () => {
    const fetchSpy = mockFetch(json(SIGNED_IN))

    const user = await authorizePassword(
      { email: ' alice@example.com ', password: 'secret password' },
      { 'x-forwarded-for': '203.0.113.7', cookie: 'next-auth.csrf-token=abc' }
    )

    expect(user).toMatchObject({ id: SIGNED_IN.id, email: 'alice@example.com', accessToken: 'backend-jwt' })
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('http://backend:8000/api/v1/auth/login')
    expect(JSON.parse(init.body)).toEqual({ email: 'alice@example.com', password: 'secret password' })
    // The client's IP is relayed for rate limiting; its cookies are not.
    expect(init.headers).toEqual({ 'Content-Type': 'application/json', 'x-forwarded-for': '203.0.113.7' })
  })

  it('does not call the backend without both fields', async () => {
    const fetchSpy = mockFetch(json(SIGNED_IN))

    expect(await authorizePassword({ email: 'alice@example.com', password: '' }, {})).toBeNull()
    expect(await authorizePassword(undefined, {})).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it.each([
    [401, LOCAL_INVALID_CREDENTIALS],
    [422, LOCAL_INVALID_CREDENTIALS],
    [429, LOCAL_TOO_MANY_ATTEMPTS],
    [500, LOCAL_SERVER_ERROR],
  ])('turns a %i into the %s error code', async (status, code) => {
    mockFetch(json({ detail: 'nope' }, status))

    await expect(
      authorizePassword({ email: 'alice@example.com', password: 'wrong password' }, {})
    ).rejects.toThrow(code)
  })

  it('reports an unreachable backend as a server error', async () => {
    mockFetch(new TypeError('fetch failed'))

    await expect(
      authorizePassword({ email: 'alice@example.com', password: 'secret password' }, {})
    ).rejects.toThrow(LOCAL_SERVER_ERROR)
  })
})

describe('passkey sign-in', () => {
  beforeEach(() => {
    process.env.BACKEND_URL = 'http://backend:8000'
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('forwards the assertion for the backend to verify', async () => {
    const fetchSpy = mockFetch(json(SIGNED_IN))
    const credential = { id: 'cred', response: { signature: 'sig' } }

    const user = await authorizePasskey({ flowId: 'flow-1', credential: JSON.stringify(credential) }, {})

    expect(user?.accessToken).toBe('backend-jwt')
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('http://backend:8000/api/v1/auth/passkeys/login/verify')
    expect(JSON.parse(init.body)).toEqual({ flow_id: 'flow-1', credential })
  })

  it('refuses an assertion the backend rejects', async () => {
    mockFetch(json({ detail: 'The passkey could not be verified.' }, 401))

    await expect(authorizePasskey({ flowId: 'flow-1', credential: '{}' }, {})).rejects.toThrow(PASSKEY_REJECTED)
  })

  it('refuses a credential that is not JSON without calling the backend', async () => {
    const fetchSpy = mockFetch(json(SIGNED_IN))

    await expect(authorizePasskey({ flowId: 'flow-1', credential: 'not json' }, {})).rejects.toThrow(
      PASSKEY_REJECTED
    )
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('session token for built-in sign-in', () => {
  const jwt = authOptions.callbacks!.jwt!

  it.each(['password', 'passkey'])('stores the backend token from %s sign-in without a second sync', async (provider) => {
    const fetchSpy = mockFetch(json({}))
    const user = { id: SIGNED_IN.id, accessToken: 'backend-jwt', backendUserId: SIGNED_IN.id, onboardingCompleted: true } as User

    const token = await jwt({
      token: {} as JWT,
      user,
      account: { provider, type: 'credentials', providerAccountId: SIGNED_IN.id } as Account,
      trigger: 'signIn',
    })

    expect(token).toMatchObject({ sub: SIGNED_IN.id, accessToken: 'backend-jwt', onboardingCompleted: true })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('takes the new token after a password change only once the backend accepts it', async () => {
    const fetchSpy = mockFetch(json({ onboarding_completed: true }))

    const token = await jwt({
      token: { accessToken: 'old-jwt' } as JWT,
      user: undefined as unknown as User,
      account: null,
      trigger: 'update',
      session: { accessToken: 'new-jwt' },
    })

    expect(token.accessToken).toBe('new-jwt')
    expect(fetchSpy.mock.calls[0][1].headers.Authorization).toBe('Bearer new-jwt')
  })

  it('keeps the old token when the backend refuses the new one', async () => {
    mockFetch(json({ detail: 'Invalid or expired token' }, 401))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const token = await jwt({
      token: { accessToken: 'old-jwt' } as JWT,
      user: undefined as unknown as User,
      account: null,
      trigger: 'update',
      session: { accessToken: 'forged' },
    })

    expect(token.accessToken).toBe('old-jwt')
  })
})
