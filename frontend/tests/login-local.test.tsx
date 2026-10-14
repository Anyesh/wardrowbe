import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LoginPage from '@/app/login/page'
import { LOCAL_INVALID_CREDENTIALS, LOCAL_TOO_MANY_ATTEMPTS } from '@/lib/auth-errors'

const nav = vi.hoisted(() => {
  const push = vi.fn()
  const replace = vi.fn()
  return {
    params: new URLSearchParams(),
    push,
    replace,
    router: { push, replace, prefetch: vi.fn(), back: vi.fn() },
  }
})

const auth = vi.hoisted(() => ({
  signIn: vi.fn(),
  getSession: vi.fn(),
  getProviders: vi.fn(),
}))

const passkeys = vi.hoisted(() => ({
  support: 'supported' as 'supported' | 'insecure' | 'unsupported',
  getPasskeyAssertion: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => nav.router,
  usePathname: () => '/login',
  useSearchParams: () => nav.params,
}))

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: 'unauthenticated' }),
  signIn: auth.signIn,
  getSession: auth.getSession,
  signOut: vi.fn(),
  getProviders: auth.getProviders,
}))

vi.mock('@/lib/passkeys', async () => {
  const actual = await vi.importActual<typeof import('@/lib/passkeys')>('@/lib/passkeys')
  return {
    ...actual,
    passkeySupport: () => passkeys.support,
    getPasskeyAssertion: passkeys.getPasskeyAssertion,
  }
})

function mockBackend({ setupRequired = false } = {}) {
  global.fetch = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    let body: unknown = { configured: true, mode: 'local', error: null }
    if (url.endsWith('/auth/config')) {
      body = {
        oidc: { enabled: false, issuer_url: null, client_id: null },
        local_auth: true,
        dev_mode: false,
        forward_auth: false,
        mobile_notice: null,
      }
    } else if (url.endsWith('/auth/setup')) {
      body = { required: setupRequired }
    }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  }) as unknown as typeof fetch
}

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LoginPage />
    </QueryClientProvider>
  )
}

async function fillAndSubmit(email: string, password: string) {
  fireEvent.change(await screen.findByLabelText('email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('local.password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'local.submit' }))
}

describe('login page with built-in sign-in', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nav.params = new URLSearchParams()
    passkeys.support = 'supported'
    auth.getProviders.mockResolvedValue({
      'forward-auth': { id: 'forward-auth', type: 'credentials' },
      password: { id: 'password', type: 'credentials' },
      passkey: { id: 'passkey', type: 'credentials' },
    })
    auth.getSession.mockResolvedValue({ accessToken: 'backend-jwt' })
    mockBackend()
  })

  it('shows the email and password form and the passkey button', async () => {
    renderLogin()

    expect(await screen.findByLabelText('email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('local.password')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'local.submit' })).toBeEnabled()
    expect(screen.getByRole('button', { name: /passkey.signIn/ })).toBeEnabled()
  })

  it('validates the fields before calling the server', async () => {
    renderLogin()

    await fillAndSubmit('not-an-email', '')

    expect(await screen.findByText('local.emailInvalid')).toBeInTheDocument()
    expect(screen.getByText('local.passwordRequired')).toBeInTheDocument()
    expect(auth.signIn).not.toHaveBeenCalled()
  })

  it('signs in with the password provider without a redirect', async () => {
    auth.signIn.mockResolvedValue({ ok: true, error: null, status: 200, url: '/dashboard' })
    renderLogin()

    await fillAndSubmit(' alice@example.com ', 'secret password')

    await waitFor(() =>
      expect(auth.signIn).toHaveBeenCalledWith('password', {
        email: 'alice@example.com',
        password: 'secret password',
        redirect: false,
      })
    )
  })

  it.each([
    [LOCAL_INVALID_CREDENTIALS, 'local.invalidCredentials'],
    ['CredentialsSignin', 'local.invalidCredentials'],
    [LOCAL_TOO_MANY_ATTEMPTS, 'local.tooManyAttempts'],
    ['Something else', 'local.serverError'],
  ])('explains a %s failure and clears the password', async (code, message) => {
    auth.signIn.mockResolvedValue({ ok: false, error: code, status: 401, url: null })
    renderLogin()

    await fillAndSubmit('alice@example.com', 'wrong password')

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByLabelText('local.password')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'local.submit' })).toBeEnabled()
  })

  it('signs in with a passkey assertion', async () => {
    passkeys.getPasskeyAssertion.mockResolvedValue({ flowId: 'flow-1', credential: '{"id":"x"}' })
    auth.signIn.mockResolvedValue({ ok: true, error: null, status: 200, url: '/dashboard' })
    renderLogin()

    fireEvent.click(await screen.findByRole('button', { name: /passkey.signIn/ }))

    await waitFor(() =>
      expect(auth.signIn).toHaveBeenCalledWith('passkey', {
        flowId: 'flow-1',
        credential: '{"id":"x"}',
        redirect: false,
      })
    )
  })

  it('explains a cancelled passkey prompt', async () => {
    const { PasskeyCeremonyError } = await import('@/lib/passkeys')
    passkeys.getPasskeyAssertion.mockRejectedValue(new PasskeyCeremonyError('cancelled'))
    renderLogin()

    fireEvent.click(await screen.findByRole('button', { name: /passkey.signIn/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('passkey.cancelled')
    expect(auth.signIn).not.toHaveBeenCalled()
  })

  it.each([
    ['insecure', 'passkey.insecure'],
    ['unsupported', 'passkey.unsupported'],
  ] as const)('disables the passkey button where passkeys are %s', async (support, message) => {
    passkeys.support = support
    renderLogin()

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /passkey.signIn/ })).toBeDisabled()
  })

  it('sends a fresh install to /setup', async () => {
    mockBackend({ setupRequired: true })
    renderLogin()

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/setup'))
  })
})
