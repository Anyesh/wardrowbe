import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { useState, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OnboardingPage from '@/app/onboarding/page'

const auth = vi.hoisted(() => ({
  current: { user: null as unknown, isAuthenticated: false, isLoading: false, session: null },
}))
const router = vi.hoisted(() => ({ push: (_url: string) => {} }))

vi.mock('@/lib/hooks/use-auth', () => ({ useAuth: () => auth.current }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: (url: string) => router.push(url), replace: vi.fn() }),
  usePathname: () => '/onboarding',
  useSearchParams: () => new URLSearchParams(),
}))

// Like the real App Router, push updates state in a component above the page, which React
// reports as an error when it happens during the page's render.
function RouterHarness({
  children,
  onNavigate,
}: {
  children: ReactNode
  onNavigate: (url: string) => void
}) {
  const [, setLocation] = useState('/onboarding')
  router.push = (url) => {
    setLocation(url)
    onNavigate(url)
  }
  const [client] = useState(() => new QueryClient())
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  consoleError.mockRestore()
})

describe('onboarding redirects', () => {
  it.each([
    ['/login', { user: null, isAuthenticated: false }],
    ['/dashboard', { user: { onboarding_completed: true }, isAuthenticated: true }],
  ])('sends the user to %s without updating state during render', async (target, state) => {
    auth.current = { ...auth.current, ...state }
    const onNavigate = vi.fn()
    // React warns once per rendering component name, so each case renames the page to keep the
    // second case from passing on a suppressed warning.
    Object.assign(OnboardingPage, { displayName: `OnboardingPage${target}` })

    render(
      <RouterHarness onNavigate={onNavigate}>
        <OnboardingPage />
      </RouterHarness>,
    )

    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith(target))
    expect(consoleError).not.toHaveBeenCalled()
  })
})
