// @vitest-environment node
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'
import { GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS } from '@/app/api/v1/[...path]/route'

function mockBackend(response: Response) {
  const spy = vi.fn().mockResolvedValue(response)
  global.fetch = spy as unknown as typeof fetch
  return spy
}

function targetOf(spy: ReturnType<typeof vi.fn>) {
  return spy.mock.calls[0][0] as string
}

function initOf(spy: ReturnType<typeof vi.fn>) {
  return spy.mock.calls[0][1] as RequestInit & { duplex?: string }
}

describe('/api/v1 catch-all proxy', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    vi.clearAllMocks()
    delete process.env.BACKEND_URL
    delete process.env.NEXT_PUBLIC_API_URL
  })

  afterEach(() => {
    process.env = { ...originalEnv }
  })

  describe('backend resolution', () => {
    it('routes to BACKEND_URL at request time', async () => {
      process.env.BACKEND_URL = 'http://renamed-backend:8000'
      const spy = mockBackend(new Response('{}', { status: 200 }))

      await GET(new NextRequest('http://localhost:3000/api/v1/users/me'))

      expect(targetOf(spy)).toBe('http://renamed-backend:8000/api/v1/users/me')
    })

    it('honors a BACKEND_URL change without re-importing the module', async () => {
      process.env.BACKEND_URL = 'http://first-host:8000'
      const first = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/health'))
      expect(targetOf(first)).toBe('http://first-host:8000/api/v1/health')

      process.env.BACKEND_URL = 'http://second-host:9999'
      const second = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/health'))
      expect(targetOf(second)).toBe('http://second-host:9999/api/v1/health')
    })

    it('falls back to NEXT_PUBLIC_API_URL then to http://backend:8000', async () => {
      process.env.NEXT_PUBLIC_API_URL = 'http://legacy-var:8000'
      const spy = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/health'))
      expect(targetOf(spy)).toBe('http://legacy-var:8000/api/v1/health')

      delete process.env.NEXT_PUBLIC_API_URL
      const fallback = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/health'))
      expect(targetOf(fallback)).toBe('http://backend:8000/api/v1/health')
    })

    it('strips a trailing slash from BACKEND_URL', async () => {
      process.env.BACKEND_URL = 'http://backend:8000/'
      const spy = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/health'))
      expect(targetOf(spy)).toBe('http://backend:8000/api/v1/health')
    })
  })

  describe('url preservation', () => {
    it('preserves the signed-url query string for images', async () => {
      const spy = mockBackend(new Response('binary', { status: 200 }))
      const url =
        'http://localhost:3000/api/v1/images/8f14e45f-ceea-467a-9d2b-1c2f3a4b5c6d/abc_thumb.jpg?expires=123&sig=xyz%2Babc'

      await GET(new NextRequest(url))

      expect(targetOf(spy)).toBe(
        'http://backend:8000/api/v1/images/8f14e45f-ceea-467a-9d2b-1c2f3a4b5c6d/abc_thumb.jpg?expires=123&sig=xyz%2Babc'
      )
    })

    it('does not re-encode already-encoded path segments', async () => {
      const spy = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/items/a%2Fb'))
      expect(targetOf(spy)).toBe('http://backend:8000/api/v1/items/a%2Fb')
    })
  })

  describe('gzip handling', () => {
    it('strips content-encoding so the decoded body is not mislabelled', async () => {
      // fetch transparently decodes gzip but leaves the header, so forwarding it
      // verbatim would make the browser try to gunzip plain bytes.
      mockBackend(
        new Response('{"items":[]}', {
          status: 200,
          headers: {
            'content-encoding': 'gzip',
            'content-length': '17',
            'content-type': 'application/json',
          },
        })
      )

      const res = await GET(new NextRequest('http://localhost:3000/api/v1/items'))

      expect(res.headers.get('content-encoding')).toBeNull()
      expect(res.headers.get('content-length')).toBeNull()
      expect(res.headers.get('content-type')).toBe('application/json')
      expect(await res.text()).toBe('{"items":[]}')
    })

    it('passes through cache-control for images', async () => {
      mockBackend(
        new Response('binary', {
          status: 200,
          headers: {
            'content-type': 'image/jpeg',
            'cache-control': 'private, max-age=3600, must-revalidate',
          },
        })
      )

      const res = await GET(new NextRequest('http://localhost:3000/api/v1/images/u/a.jpg'))

      expect(res.headers.get('cache-control')).toBe('private, max-age=3600, must-revalidate')
      expect(res.headers.get('content-type')).toBe('image/jpeg')
    })
  })

  describe('request headers', () => {
    it('forwards authorization and strips hop-by-hop headers', async () => {
      const spy = mockBackend(new Response('{}', { status: 200 }))

      await GET(
        new NextRequest('http://localhost:3000/api/v1/users/me', {
          headers: {
            authorization: 'Bearer token-123',
            cookie: 'session=abc',
            host: 'localhost:3000',
            connection: 'keep-alive',
            'transfer-encoding': 'chunked',
          },
        })
      )

      const headers = new Headers(initOf(spy).headers)
      expect(headers.get('authorization')).toBe('Bearer token-123')
      expect(headers.get('cookie')).toBe('session=abc')
      expect(headers.get('host')).toBeNull()
      expect(headers.get('connection')).toBeNull()
      expect(headers.get('transfer-encoding')).toBeNull()
    })
  })

  describe('methods and bodies', () => {
    it('sends no body on GET', async () => {
      const spy = mockBackend(new Response('{}', { status: 200 }))
      await GET(new NextRequest('http://localhost:3000/api/v1/items'))
      expect(initOf(spy).body).toBeUndefined()
      expect(initOf(spy).duplex).toBeUndefined()
    })

    it('streams the body with duplex half on POST', async () => {
      const spy = mockBackend(new Response('{}', { status: 201 }))
      await POST(
        new NextRequest('http://localhost:3000/api/v1/items', {
          method: 'POST',
          body: 'multipart-payload',
        })
      )
      const init = initOf(spy)
      expect(init.method).toBe('POST')
      expect(init.body).toBeTruthy()
      expect(init.duplex).toBe('half')
    })

    it.each([
      ['PUT', PUT],
      ['PATCH', PATCH],
      ['DELETE', DELETE],
    ])('forwards %s', async (method, handler) => {
      const spy = mockBackend(new Response(null, { status: 204 }))
      await handler(new NextRequest('http://localhost:3000/api/v1/items/1', { method }))
      expect(initOf(spy).method).toBe(method)
    })

    it('forwards HEAD and OPTIONS without a body', async () => {
      const headSpy = mockBackend(new Response(null, { status: 200 }))
      await HEAD(new NextRequest('http://localhost:3000/api/v1/items', { method: 'HEAD' }))
      expect(initOf(headSpy).body).toBeUndefined()

      const optSpy = mockBackend(new Response(null, { status: 204 }))
      await OPTIONS(new NextRequest('http://localhost:3000/api/v1/items', { method: 'OPTIONS' }))
      expect(initOf(optSpy).method).toBe('OPTIONS')
    })
  })

  describe('status and error handling', () => {
    it('preserves non-2xx status and body', async () => {
      mockBackend(new Response('{"detail":"Not authenticated"}', { status: 401 }))
      const res = await GET(new NextRequest('http://localhost:3000/api/v1/users/me'))
      expect(res.status).toBe(401)
      expect(await res.json()).toEqual({ detail: 'Not authenticated' })
    })

    it('forwards a 302 to a custom scheme without following it', async () => {
      // auth/mobile-callback redirects to wardrobe://auth/callback. fetch's default
      // redirect:'follow' throws on a non-http scheme, so the proxy must not follow.
      const spy = mockBackend(
        new Response(null, {
          status: 302,
          headers: { location: 'wardrobe://auth/callback?code=abc' },
        })
      )

      const res = await GET(new NextRequest('http://localhost:3000/api/v1/auth/mobile-callback?code=abc'))

      expect(initOf(spy).redirect).toBe('manual')
      expect(res.status).toBe(302)
      expect(res.headers.get('location')).toBe('wardrobe://auth/callback?code=abc')
    })

    it('returns 502 with the unreachable host when dns fails', async () => {
      process.env.BACKEND_URL = 'http://backend:8000'
      global.fetch = vi.fn().mockRejectedValue(
        Object.assign(new Error('getaddrinfo EAI_AGAIN backend'), { code: 'EAI_AGAIN' })
      ) as unknown as typeof fetch

      const res = await GET(new NextRequest('http://localhost:3000/api/v1/users/me'))

      expect(res.status).toBe(502)
      const body = await res.json()
      expect(body.detail).toContain('http://backend:8000')
    })
  })
})
