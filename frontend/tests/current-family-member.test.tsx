import type { ComponentType } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FamilyPage from '@/app/dashboard/family/page'
import FamilyFeedPage from '@/app/dashboard/family/feed/page'
import { useCurrentFamilyMember, useFamily } from '@/lib/hooks/use-family'
import { useFamilyOutfits } from '@/lib/hooks/use-outfits'
import { useUserProfile } from '@/lib/hooks/use-user'
import type { Family } from '@/lib/types'

vi.mock('@/lib/hooks/use-user', () => ({ useUserProfile: vi.fn() }))
vi.mock('@/lib/hooks/use-family', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/hooks/use-family')>()),
  useFamily: vi.fn(),
}))
vi.mock('@/lib/hooks/use-outfits', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/hooks/use-outfits')>()),
  useFamilyOutfits: vi.fn(),
}))

const family: Family = {
  id: 'family',
  name: 'Household',
  invite_code: 'code',
  pending_invites: [],
  created_at: '2026-01-01T00:00:00Z',
  members: [
    {
      id: 'detached-admin',
      display_name: 'Admin Person',
      email: 'detached-admin@detached.invalid',
      role: 'admin',
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'member',
      display_name: 'Member Person',
      email: 'member@example.com',
      role: 'member',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

const profileLoading = { data: undefined, isPending: true, isError: false }
const profileFailed = { data: undefined, isPending: false, isError: true }
const profileOfAdmin = { data: { id: 'detached-admin' }, isPending: false, isError: false }

function mockProfile(profile: typeof profileLoading | typeof profileOfAdmin) {
  vi.mocked(useUserProfile).mockReturnValue(
    profile as unknown as ReturnType<typeof useUserProfile>
  )
}

function renderPage(Page: ComponentType) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Page />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useFamily).mockReturnValue({
    data: family,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useFamily>)
  vi.mocked(useFamilyOutfits).mockReturnValue({
    data: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useFamilyOutfits>)
})

describe('useCurrentFamilyMember', () => {
  it.each([
    [
      'a detached admin by user id',
      family,
      profileOfAdmin,
      { memberId: 'detached-admin', isPending: false, isError: false },
    ],
    [
      'nobody while the profile loads',
      family,
      profileLoading,
      { memberId: undefined, isPending: true, isError: false },
    ],
    [
      'nobody when the profile fails',
      family,
      profileFailed,
      { memberId: undefined, isPending: false, isError: true },
    ],
    [
      'nobody while the family loads',
      undefined,
      profileOfAdmin,
      { memberId: undefined, isPending: false, isError: false },
    ],
  ])('finds %s', (_case, loadedFamily, profile, expected) => {
    mockProfile(profile)

    const { result } = renderHook(() => useCurrentFamilyMember(loadedFamily))

    expect({
      memberId: result.current.member?.id,
      isPending: result.current.isPending,
      isError: result.current.isError,
    }).toEqual(expected)
  })
})

describe('pages that depend on the current member', () => {
  it.each([
    ['while the profile loads', profileLoading, [], ['Admin', 'Member', 'pageLoad.title'], undefined],
    ['when the profile fails', profileFailed, ['pageLoad.title'], ['Admin', 'Member'], undefined],
    ['once the profile loads', profileOfAdmin, ['Member'], ['Admin', 'pageLoad.title'], 'member'],
  ])(
    'the feed never offers the user their own outfits %s',
    (_case, profile, shown, hidden, activeMemberId) => {
      mockProfile(profile)

      renderPage(FamilyFeedPage)

      for (const text of shown) expect(screen.getByText(text)).toBeInTheDocument()
      for (const text of hidden) expect(screen.queryByText(text)).not.toBeInTheDocument()
      expect(useFamilyOutfits).not.toHaveBeenCalledWith('detached-admin')
      expect(useFamilyOutfits).toHaveBeenLastCalledWith(activeMemberId)
    }
  )

  it.each([
    ['while the profile loads', profileLoading, [], ['Household', 'sendInviteDesc', 'pageLoad.title']],
    ['when the profile fails', profileFailed, ['pageLoad.title'], ['Household', 'sendInviteDesc']],
    ['once the profile loads', profileOfAdmin, ['Household', 'sendInviteDesc'], ['pageLoad.title']],
  ])('the family page decides admin controls only %s', (_case, profile, shown, hidden) => {
    mockProfile(profile)

    renderPage(FamilyPage)

    for (const text of shown) expect(screen.getByText(text)).toBeInTheDocument()
    for (const text of hidden) expect(screen.queryByText(text)).not.toBeInTheDocument()
  })
})
