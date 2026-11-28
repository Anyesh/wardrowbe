import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api'
import { useJoinFamilyByToken } from '@/lib/hooks/use-family'
import InvitePage from '@/app/invite/page'

vi.unmock('next-intl')
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 'token' }, status: 'authenticated' }),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('token=invite-token'),
}))

vi.mock('@/lib/hooks/use-family', () => ({ useJoinFamilyByToken: vi.fn() }))

const catalog = (namespace: string) =>
  JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', 'en', `${namespace}.json`), 'utf8'),
  )
const messages = { auth: catalog('auth'), errors: catalog('errors') }

function renderPage() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <InvitePage />
    </NextIntlClientProvider>,
  )
}

describe('InvitePage join errors', () => {
  it.each([
    ['an unverified email', 403, 'EMAIL_NOT_VERIFIED'],
    ['an invite for another email', 403, 'INVITE_EMAIL_MISMATCH'],
    ['an invalid link', 404, 'INVITE_LINK_INVALID'],
    ['an existing family', 409, 'ALREADY_IN_FAMILY'],
  ])('shows the translated message for %s', (_case, status, code) => {
    const expected = messages.errors[code]
    vi.mocked(useJoinFamilyByToken).mockReturnValue({
      isError: true,
      error: new ApiError('English', status, { detail: 'English', error_code: code }),
      isPending: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof useJoinFamilyByToken>)

    renderPage()

    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('falls back to the default message for an uncoded error', () => {
    vi.mocked(useJoinFamilyByToken).mockReturnValue({
      isError: true,
      error: new ApiError('Not Found', 404, { detail: 'Not Found' }),
      isPending: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof useJoinFamilyByToken>)

    renderPage()

    expect(screen.getByText(messages.errors.default)).toBeInTheDocument()
  })
})
