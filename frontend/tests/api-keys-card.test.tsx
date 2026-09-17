import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { ApiKeysCard } from '@/components/settings/api-keys-card'

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function response(data: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data } as Response
}

const activeKey = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Automation',
  scopes: ['items:read'],
  expires_at: null,
  revoked_at: null,
  last_used_at: null,
  created_at: '2026-09-17T08:00:00Z',
}

describe('ApiKeysCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(global.fetch).mockReset()
  })

  it('creates a scoped API key and shows its token once', async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ ...activeKey, token: 'wrb_secret-token' }, 201))
      .mockResolvedValueOnce(response([activeKey]))

    render(<ApiKeysCard />, { wrapper: wrapper() })

    fireEvent.click(await screen.findByText('apiKeys.create'))
    fireEvent.change(screen.getByLabelText('apiKeys.name'), { target: { value: 'Automation' } })
    fireEvent.click(screen.getByLabelText('apiKeys.scopes.imagesRead'))
    fireEvent.click(screen.getByText('apiKeys.createKey'))

    expect(await screen.findByText('wrb_secret-token')).toBeInTheDocument()
    expect(screen.getByText('apiKeys.tokenWarning')).toBeInTheDocument()

    const createCall = vi.mocked(global.fetch).mock.calls.find(([, init]) => init?.method === 'POST')
    expect(createCall?.[0]).toBe('/api/v1/auth/api-keys')
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      name: 'Automation',
      scopes: ['items:read', 'images:read'],
      expires_at: null,
    })
  })

  it('revokes an active API key', async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response([activeKey]))
      .mockResolvedValueOnce(response({ ...activeKey, revoked_at: '2026-09-17T09:00:00Z' }))
      .mockResolvedValueOnce(response([{ ...activeKey, revoked_at: '2026-09-17T09:00:00Z' }]))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApiKeysCard />, { wrapper: wrapper() })

    expect(await screen.findByText('Automation')).toBeInTheDocument()
    fireEvent.click(screen.getByText('apiKeys.revoke'))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/auth/api-keys/${activeKey.id}/revoke`,
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('deletes a revoked API key', async () => {
    const revokedKey = { ...activeKey, revoked_at: '2026-09-17T09:00:00Z' }
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(response([revokedKey]))
      .mockResolvedValueOnce(response(undefined, 204))
      .mockResolvedValueOnce(response([]))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApiKeysCard />, { wrapper: wrapper() })

    expect(await screen.findByText('Automation')).toBeInTheDocument()
    fireEvent.click(screen.getByText('apiKeys.delete'))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/auth/api-keys/${activeKey.id}`,
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

})
