import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api'
import { useJoinFamilyByToken } from '@/lib/hooks/use-family'
import InvitePage from '@/app/invite/page'

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 'token' }, status: 'authenticated' }),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('token=invite-token'),
}))

vi.mock('@/lib/hooks/use-family', () => ({ useJoinFamilyByToken: vi.fn() }))

describe('InvitePage join errors', () => {
  it.each([
    [
      'an unverified email',
      new ApiError('Forbidden', 403, {
        detail: { message: 'not verified', error_code: 'EMAIL_NOT_VERIFIED' },
      }),
      'invite.emailNotVerified',
    ],
    [
      'an invite for another email',
      new ApiError('Forbidden', 403, {
        detail: 'This invite was sent to a different email address',
      }),
      'invite.wrongEmail',
    ],
  ])('explains a 403 for %s', (_case, error, message) => {
    vi.mocked(useJoinFamilyByToken).mockReturnValue({
      isError: true,
      error,
      isPending: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof useJoinFamilyByToken>)

    render(<InvitePage />)

    expect(screen.getByText(message)).toBeInTheDocument()
  })
})
