import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import SettingsPage from '@/app/dashboard/settings/page'

vi.mock('@/lib/hooks/use-preferences', () => {
  const preferences = {}
  return {
    usePreferences: () => ({ data: preferences, isLoading: false }),
    useUpdatePreferences: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useResetPreferences: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useTestAIEndpoint: () => ({ mutateAsync: vi.fn() }),
  }
})

vi.mock('@/lib/hooks/use-user', () => {
  const profile = { display_name: 'Test User', email: 'test@example.com' }
  return {
    useUserProfile: () => ({ data: profile, isLoading: false }),
    useUpdateUserProfile: () => ({ isPending: false, mutateAsync: vi.fn() }),
  }
})

vi.mock('@/components/ui/slider', () => ({ Slider: () => <div /> }))
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingColors: () => [],
  useOccasions: () => [],
}))

describe('Settings API keys', () => {
  it('shows API key management in settings', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    vi.mocked(global.fetch).mockResolvedValueOnce({ ok: true, status: 200, json: async () => [] } as Response)
    render(<QueryClientProvider client={client}><SettingsPage /></QueryClientProvider>)
    expect(screen.getByText('apiKeys.title')).toBeInTheDocument()
  })
})
