import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AiRouteGuard } from '@/components/ai-route-guard'

const navigation = vi.hoisted(() => ({ pathname: '/dashboard/suggest', replace: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: navigation.replace, push: vi.fn() }),
  usePathname: () => navigation.pathname,
}))

function mockFeatures(response: Response | Promise<Response>) {
  global.fetch = vi.fn(() => Promise.resolve(response)) as unknown as typeof fetch
}

function featuresResponse(aiUiEnabled: boolean) {
  return new Response(
    JSON.stringify({ background_removal: false, max_upload_size_mb: 20, ai_ui_enabled: aiUiEnabled }),
    { status: 200 }
  )
}

function renderGuard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AiRouteGuard>
        <p>page body</p>
      </AiRouteGuard>
    </QueryClientProvider>
  )
}

describe('AiRouteGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    navigation.pathname = '/dashboard/suggest'
  })

  it.each(['/dashboard/suggest', '/dashboard/pairings', '/dashboard/learning'])(
    'sends %s back to the dashboard when the AI UI is off',
    async (pathname) => {
      navigation.pathname = pathname
      mockFeatures(featuresResponse(false))
      renderGuard()
      await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/dashboard'))
      expect(screen.queryByText('page body')).not.toBeInTheDocument()
    }
  )

  it('shows an AI page when the AI UI is on', async () => {
    mockFeatures(featuresResponse(true))
    renderGuard()
    expect(await screen.findByText('page body')).toBeInTheDocument()
    expect(navigation.replace).not.toHaveBeenCalled()
  })

  it('shows an AI page when the features call fails', async () => {
    mockFeatures(new Response('boom', { status: 500 }))
    renderGuard()
    expect(await screen.findByText('page body')).toBeInTheDocument()
    expect(navigation.replace).not.toHaveBeenCalled()
  })

  it('holds an AI page back until the features call answers', () => {
    mockFeatures(new Promise<Response>(() => {}))
    renderGuard()
    expect(screen.queryByText('page body')).not.toBeInTheDocument()
  })

  it('never holds back or redirects a manual page', async () => {
    navigation.pathname = '/dashboard/outfits'
    mockFeatures(featuresResponse(false))
    renderGuard()
    expect(screen.getByText('page body')).toBeInTheDocument()
    await waitFor(() => expect(global.fetch).toHaveBeenCalled())
    expect(navigation.replace).not.toHaveBeenCalled()
  })
})
