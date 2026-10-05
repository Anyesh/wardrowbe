import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { signOut } from 'next-auth/react'
import { Header } from '@/components/header'

vi.mock('@/components/locale-switcher', () => ({ LocaleSwitcher: () => null }))

function mockAuthConfig(forwardAuth: boolean) {
  global.fetch = vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          oidc: { enabled: false, issuer_url: null, client_id: null },
          dev_mode: false,
          forward_auth: forwardAuth,
          mobile_notice: null,
        }),
        { status: 200 }
      )
    )
  ) as unknown as typeof fetch
}

function renderHeader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Header />
    </QueryClientProvider>
  )
  return client
}

describe('header logout', () => {
  const originalLocation = window.location
  const assign = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(signOut).mockResolvedValue(undefined as never)
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, assign },
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
  })

  it('ends the proxy session through /auth/logout in forward-auth mode', async () => {
    mockAuthConfig(true)
    const client = renderHeader()
    await waitFor(() => expect(client.getQueryData(['auth-config'])).toBeDefined())

    fireEvent.click(screen.getByRole('button', { name: 'signOut' }))

    await waitFor(() => expect(assign).toHaveBeenCalledWith('/auth/logout'))
    expect(signOut).toHaveBeenCalledWith({ redirect: false })
  })

  it('keeps the NextAuth sign-out redirect outside forward-auth mode', async () => {
    mockAuthConfig(false)
    const client = renderHeader()
    await waitFor(() => expect(client.getQueryData(['auth-config'])).toBeDefined())

    fireEvent.click(screen.getByRole('button', { name: 'signOut' }))

    await waitFor(() => expect(signOut).toHaveBeenCalledWith({ callbackUrl: '/login' }))
    expect(assign).not.toHaveBeenCalled()
  })
})
