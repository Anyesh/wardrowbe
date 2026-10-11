// @vitest-environment node
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'
import { GET } from '@/app/auth/logout/route'

const SESSION = 'next-auth.session-token'

function logoutRequest(cookies: Record<string, string> = {}) {
  const headers = new Headers()
  const cookieHeader = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ')
  if (cookieHeader) headers.set('cookie', cookieHeader)
  return new NextRequest('http://wardrobe.example.com/auth/logout', { headers })
}

function clearedCookies(response: Response) {
  return response.headers
    .getSetCookie()
    .filter((c) => /Max-Age=0/i.test(c))
    .map((c) => c.split('=')[0])
    .sort()
}

describe('/auth/logout', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    process.env.NEXTAUTH_URL = 'https://wardrobe.example.com'
    delete process.env.FORWARD_AUTH_LOGOUT_URL
    delete process.env.TINYAUTH_URL
    delete process.env.OIDC_END_SESSION_URL
  })

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  it('clears every session cookie itself instead of bouncing through /api/auth/signout', async () => {
    const response = await GET(
      logoutRequest({ [`${SESSION}.0`]: 'a', [`${SESSION}.1`]: 'b', 'next-auth.csrf-token': 'keep' })
    )

    expect(clearedCookies(response)).toEqual([`${SESSION}.0`, `${SESSION}.1`])
    expect(response.headers.get('location')).not.toContain('/api/auth/signout')
  })

  it('goes straight to the logged-out login page when no proxy logout URL is set', async () => {
    const response = await GET(logoutRequest())

    expect(response.status).toBe(302)
    expect(response.headers.get('location')).toBe('https://wardrobe.example.com/login?loggedOut=1')
  })

  it('sends the user through TinyAuth logout with a redirect_uri back to the logged-out page', async () => {
    process.env.TINYAUTH_URL = 'https://auth.example.com/'

    const response = await GET(logoutRequest())

    const location = new URL(response.headers.get('location')!)
    expect(`${location.origin}${location.pathname}`).toBe('https://auth.example.com/logout')
    expect(location.searchParams.get('redirect_uri')).toBe('https://wardrobe.example.com/login?loggedOut=1')
  })

  it('uses FORWARD_AUTH_LOGOUT_URL verbatim and prefers it over TinyAuth', async () => {
    const authelia =
      'https://auth.example.com/logout?rd=https%3A%2F%2Fwardrobe.example.com%2Flogin%3FloggedOut%3D1'
    process.env.FORWARD_AUTH_LOGOUT_URL = authelia
    process.env.TINYAUTH_URL = 'https://tinyauth.example.com'

    const response = await GET(logoutRequest())

    expect(response.status).toBe(302)
    expect(response.headers.get('location')).toBe(authelia)
  })

  it('falls back to the OIDC end-session URL when no proxy logout URL is set', async () => {
    process.env.OIDC_END_SESSION_URL = 'https://idp.example.com/end-session'

    const response = await GET(logoutRequest())

    const location = new URL(response.headers.get('location')!)
    expect(`${location.origin}${location.pathname}`).toBe('https://idp.example.com/end-session')
    expect(location.searchParams.get('post_logout_redirect_uri')).toBe(
      'https://wardrobe.example.com/login?loggedOut=1'
    )
  })
})
