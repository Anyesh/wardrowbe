import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Sidebar } from '@/components/sidebar'
import { MobileSidebar } from '@/components/mobile-sidebar'
import { MobileNav } from '@/components/mobile-nav'

const AI_HREFS = ['/dashboard/suggest', '/dashboard/pairings', '/dashboard/learning']

const NAVS = {
  'desktop sidebar': () => <Sidebar />,
  'mobile sidebar': () => <MobileSidebar open onClose={() => {}} />,
  'mobile bottom nav': () => <MobileNav />,
}

function mockFeatures(response: Response | Promise<Response>) {
  global.fetch = vi.fn(() => Promise.resolve(response)) as unknown as typeof fetch
}

function featuresResponse(body: Record<string, unknown>) {
  return new Response(
    JSON.stringify({ background_removal: false, max_upload_size_mb: 20, ...body }),
    { status: 200 }
  )
}

function renderNav(nav: () => React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}>{nav()}</QueryClientProvider>)
}

function hrefs() {
  return screen.getAllByRole('link').map((link) => link.getAttribute('href'))
}

describe.each(Object.entries(NAVS))('AI entries in the %s', (_, nav) => {
  beforeEach(() => vi.clearAllMocks())

  it('are hidden when the server turns the AI UI off', async () => {
    mockFeatures(featuresResponse({ ai_ui_enabled: false }))
    renderNav(nav)
    await waitFor(() => expect(global.fetch).toHaveBeenCalled())
    await waitFor(() => expect(hrefs()).toContain('/dashboard/outfits'))
    for (const href of AI_HREFS) expect(hrefs()).not.toContain(href)
  })

  it('are shown when the server leaves the AI UI on', async () => {
    mockFeatures(featuresResponse({ ai_ui_enabled: true }))
    renderNav(nav)
    await waitFor(() => expect(hrefs()).toContain('/dashboard/suggest'))
  })

  it('are shown when the server does not send the flag', async () => {
    mockFeatures(featuresResponse({}))
    renderNav(nav)
    await waitFor(() => expect(hrefs()).toContain('/dashboard/suggest'))
  })

  it('are shown when the features call fails', async () => {
    mockFeatures(new Response('boom', { status: 500 }))
    renderNav(nav)
    await waitFor(() => expect(hrefs()).toContain('/dashboard/suggest'))
  })

  it('are not shown before the features call answers', () => {
    mockFeatures(new Promise<Response>(() => {}))
    renderNav(nav)
    expect(hrefs()).toContain('/dashboard/outfits')
    expect(hrefs()).not.toContain('/dashboard/suggest')
  })
})
