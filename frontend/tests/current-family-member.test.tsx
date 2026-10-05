import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useCurrentFamilyMember } from '@/lib/hooks/use-family'
import { useUserProfile } from '@/lib/hooks/use-user'
import type { Family } from '@/lib/types'

vi.mock('@/lib/hooks/use-user', () => ({ useUserProfile: vi.fn() }))

const family: Family = {
  id: 'family',
  name: 'Family',
  invite_code: 'code',
  pending_invites: [],
  created_at: '2026-01-01T00:00:00Z',
  members: [
    {
      id: 'detached-admin',
      display_name: 'Admin',
      email: 'detached-admin@detached.invalid',
      role: 'admin',
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'member',
      display_name: 'Member',
      email: 'member@example.com',
      role: 'member',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

describe('useCurrentFamilyMember', () => {
  it.each([
    ['a detached admin by user id', family, { id: 'detached-admin' }, 'detached-admin'],
    ['nobody while the profile loads', family, undefined, undefined],
    ['nobody while the family loads', undefined, { id: 'detached-admin' }, undefined],
  ])('finds %s', (_case, loadedFamily, profile, expectedId) => {
    vi.mocked(useUserProfile).mockReturnValue({
      data: profile,
    } as unknown as ReturnType<typeof useUserProfile>)

    const { result } = renderHook(() => useCurrentFamilyMember(loadedFamily))

    expect(result.current?.id).toBe(expectedId)
  })
})
