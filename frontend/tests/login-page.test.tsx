import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LoginPage from '@/app/login/page'
import { FORWARD_AUTH_ACCOUNT_CONFLICT, FORWARD_AUTH_SERVER_ERROR } from '@/lib/auth-errors'

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
}))

const auth = vi.hoisted(() => ({
  signIn: vi.fn(),
  getProviders: vi.fn(),
  status: 'unauthenticated' as 'loading' | 'authenticated' | 'unauthenticated',
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/login',
  useSearchParams: () => nav.params,
}))

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: auth.status }),
  signIn: auth.signIn,
  signOut: vi.fn(),
  getProviders: auth.getProviders,
}))

function mockBackend(config: { forward_auth: boolean }) {
  global.fetch = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/auth/config')
      ? { oidc: { enabled: false, issuer_url: null, client_id: null }, dev_mode: false, mobile_notice: null, ...config }
      : { configured: true, mode: 'forward-auth', error: null }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  }) as unknown as typeof fetch
}

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const tree = () => (
    <QueryClientProvider client={client}>
      <LoginPage />
    </QueryClientProvider>
  )
  const view = render(tree())
  return { ...view, rerender: () => view.rerender(tree()) }
}

describe('login page in forward-auth mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nav.params = new URLSearchParams()
    auth.status = 'unauthenticated'
    auth.getProviders.mockResolvedValue({
      'forward-auth': { id: 'forward-auth', type: 'credentials' },
    })
    auth.signIn.mockResolvedValue({ ok: true, error: null, status: 200, url: '/dashboard' })
    mockBackend({ forward_auth: true })
  })

  it('signs in through the proxy automatically without a redirect', async () => {
    renderLogin()

    await waitFor(() => expect(auth.signIn).toHaveBeenCalledTimes(1))
    expect(auth.signIn).toHaveBeenCalledWith('forward-auth', { redirect: false })
  })

  it('signs in only once even when the page re-renders', async () => {
    const view = renderLogin()
    await waitFor(() => expect(auth.signIn).toHaveBeenCalledTimes(1))

    view.rerender()

    await new Promise((r) => setTimeout(r, 20))
    expect(auth.signIn).toHaveBeenCalledTimes(1)
  })

  it('shows the missing-headers error when the proxy sign-in fails', async () => {
    auth.signIn.mockResolvedValue({ ok: false, error: 'CredentialsSignin', status: 401, url: null })

    renderLogin()

    expect(await screen.findByText('forwardAuth.headersMissing')).toBeInTheDocument()
  })

  it('shows a server error instead of blaming the proxy when the backend fails', async () => {
    auth.signIn.mockResolvedValue({ ok: false, error: FORWARD_AUTH_SERVER_ERROR, status: 401, url: null })

    renderLogin()

    expect(await screen.findByText('forwardAuth.serverError')).toBeInTheDocument()
    expect(screen.queryByText('forwardAuth.headersMissing')).not.toBeInTheDocument()
  })

  it('shows an account conflict instead of a server error when the email belongs to another account', async () => {
    auth.signIn.mockResolvedValue({ ok: false, error: FORWARD_AUTH_ACCOUNT_CONFLICT, status: 401, url: null })

    renderLogin()

    expect(await screen.findByText('forwardAuth.accountConflict')).toBeInTheDocument()
    expect(screen.queryByText('forwardAuth.serverError')).not.toBeInTheDocument()
    expect(screen.queryByText('forwardAuth.headersMissing')).not.toBeInTheDocument()
  })

  it('shows the account conflict carried in the error query parameter', async () => {
    nav.params = new URLSearchParams(`error=${FORWARD_AUTH_ACCOUNT_CONFLICT}`)

    renderLogin()

    expect(await screen.findByText('forwardAuth.accountConflict')).toBeInTheDocument()
    expect(auth.signIn).not.toHaveBeenCalled()
  })

  it('shows the server error carried in the error query parameter', async () => {
    nav.params = new URLSearchParams(`error=${FORWARD_AUTH_SERVER_ERROR}`)

    renderLogin()

    expect(await screen.findByText('forwardAuth.serverError')).toBeInTheDocument()
    expect(auth.signIn).not.toHaveBeenCalled()
  })

  it.each([
    ['an error', 'error=CredentialsSignin'],
    ['a logout', 'loggedOut=1'],
  ])('does not sign in automatically after %s', async (_label, query) => {
    nav.params = new URLSearchParams(query)

    renderLogin()

    const button = await screen.findByRole('button', { name: 'forwardAuth.continue' })
    expect(auth.signIn).not.toHaveBeenCalled()

    fireEvent.click(button)
    await waitFor(() => expect(auth.signIn).toHaveBeenCalledWith('forward-auth', { redirect: false }))
  })

  it('does not sign in again when a session already exists', async () => {
    auth.status = 'authenticated'

    renderLogin()

    await new Promise((r) => setTimeout(r, 20))
    expect(auth.signIn).not.toHaveBeenCalled()
  })
})

describe('login page without forward-auth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nav.params = new URLSearchParams()
    auth.status = 'unauthenticated'
    mockBackend({ forward_auth: false })
  })

  it('keeps the dev login form and never calls the proxy provider', async () => {
    auth.getProviders.mockResolvedValue({
      'forward-auth': { id: 'forward-auth', type: 'credentials' },
      'dev-credentials': { id: 'dev-credentials', type: 'credentials' },
    })

    renderLogin()

    expect(await screen.findByText('devMode')).toBeInTheDocument()
    expect(auth.signIn).not.toHaveBeenCalled()
  })
})
