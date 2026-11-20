import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TryOnPanel } from '@/components/outfits/try-on-panel'
import { TryOnPhotoCard } from '@/components/settings/try-on-photo-card'
import { ApiError, api } from '@/lib/api'
import { queryKeys } from '@/lib/hooks/query-keys'
import { useTryOnEnabled } from '@/lib/hooks/use-features'
import { isTakingLonger, pollInterval, tryOnErrorCode, type TryOn } from '@/lib/hooks/use-try-on'

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
}))

vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}))

function wrapperFor(features?: Record<string, unknown>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  if (features) client.setQueryData(queryKeys.features, features)
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

const BASE = { background_removal: false, max_upload_size_mb: 20 }

beforeEach(() => {
  vi.mocked(api.get).mockReset()
  vi.mocked(api.post).mockReset()
  vi.mocked(api.delete).mockReset()
})

describe('useTryOnEnabled', () => {
  it.each([
    ['explicitly on', { ...BASE, try_on_enabled: true }, true],
    ['on with the AI UI switch on', { ...BASE, try_on_enabled: true, ai_ui_enabled: true }, true],
    ['on but the AI UI switch is off', { ...BASE, try_on_enabled: true, ai_ui_enabled: false }, false],
    ['explicitly off', { ...BASE, try_on_enabled: false }, false],
    ['flag missing (older backend)', { ...BASE }, false],
    ['not a boolean true', { ...BASE, try_on_enabled: 'yes' }, false],
  ])('is %s', (_name, features, expected) => {
    const { result } = renderHook(() => useTryOnEnabled(), { wrapper: wrapperFor(features) })
    expect(result.current).toBe(expected)
  })

  it('is false while the features call is loading', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useTryOnEnabled(), { wrapper: wrapperFor() })
    expect(result.current).toBe(false)
  })

  it('is false when the features call fails', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('down'))
    const { result } = renderHook(() => useTryOnEnabled(), { wrapper: wrapperFor() })
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(result.current).toBe(false)
  })
})

describe('try-on helpers', () => {
  const tryOn = (status: TryOn['status'], createdAt: string): TryOn => ({
    status,
    image_url: null,
    medium_url: null,
    error_code: null,
    created_at: createdAt,
    stale: false,
  })

  it('polls only while pending: fast, then slowly past four minutes, then gives up', () => {
    const now = Date.parse('2026-11-12T10:30:00Z')
    expect(pollInterval(tryOn('pending', '2026-11-12T10:29:00Z'), now)).toBe(2000)
    expect(pollInterval(tryOn('pending', '2026-11-12T10:25:00Z'), now)).toBe(15000)
    // still polled until the server reports it as retryable (15 minutes), then a bit longer
    expect(pollInterval(tryOn('pending', '2026-11-12T10:14:00Z'), now)).toBe(15000)
    expect(pollInterval(tryOn('pending', '2026-11-12T10:05:00Z'), now)).toBe(false)
    expect(pollInterval(tryOn('ready', '2026-11-12T10:29:00Z'), now)).toBe(false)
    expect(pollInterval(null, now)).toBe(false)
  })

  it('says a pending try-on is taking longer after four minutes', () => {
    const now = Date.parse('2026-11-12T10:10:00Z')
    expect(isTakingLonger(tryOn('pending', '2026-11-12T10:09:00Z'), now)).toBe(false)
    expect(isTakingLonger(tryOn('pending', '2026-11-12T10:05:00Z'), now)).toBe(true)
    expect(isTakingLonger(tryOn('ready', '2026-11-12T10:00:00Z'), now)).toBe(false)
    expect(isTakingLonger(null, now)).toBe(false)
  })

  it('reads the error code out of an ApiError', () => {
    const error = new ApiError('x', 409, { detail: { error_code: 'TRY_ON_NO_PHOTO' } })
    expect(tryOnErrorCode(error)).toBe('TRY_ON_NO_PHOTO')
    expect(tryOnErrorCode(new ApiError('x', 500, {}))).toBeNull()
    expect(tryOnErrorCode(new Error('x'))).toBeNull()
  })
})

const ON = { ...BASE, try_on_enabled: true }
const PHOTO = { image_url: '/p.jpg', medium_url: '/p-m.jpg', created_at: '', updated_at: '' }

function notFound(code: string) {
  return new ApiError('nope', 404, { detail: { error_code: code } })
}

function mockApi(photo: unknown, tryOn: unknown) {
  vi.mocked(api.get).mockImplementation(async (path: string) => {
    if (path === '/users/me/try-on-photo') {
      if (photo) return photo
      throw notFound('TRY_ON_NO_PHOTO')
    }
    if (path.endsWith('/try-on')) {
      if (tryOn) return tryOn
      throw notFound('TRY_ON_NONE')
    }
    return {}
  })
}

describe('TryOnPanel', () => {
  it('renders nothing when try-on is disabled', () => {
    const { container } = render(<TryOnPanel outfitId="o1" />, {
      wrapper: wrapperFor({ ...BASE, try_on_enabled: false }),
    })
    expect(container).toBeEmptyDOMElement()
    expect(api.get).not.toHaveBeenCalled()
  })

  it('offers to add a photo when there is none', async () => {
    mockApi(null, null)
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    const link = await screen.findByRole('link', { name: 'addPhoto' })
    expect(link).toHaveAttribute('href', '/dashboard/settings#try-on-photo')
    expect(screen.queryByText('seeIt')).not.toBeInTheDocument()
  })

  it('shows the generate button once there is a photo and starts a generation', async () => {
    mockApi(PHOTO, null)
    vi.mocked(api.post).mockResolvedValue({ status: 'pending', created_at: new Date().toISOString() })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    fireEvent.click(await screen.findByRole('button', { name: 'seeIt' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/outfits/o1/try-on'))
  })

  it('shows the drawing state while pending', async () => {
    mockApi(PHOTO, { status: 'pending', created_at: new Date().toISOString(), stale: false })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    expect(await screen.findByRole('status')).toHaveTextContent('drawing')
    expect(screen.queryByRole('button', { name: 'seeIt' })).not.toBeInTheDocument()
  })

  it('shows the image with regenerate and delete when ready', async () => {
    mockApi(PHOTO, {
      status: 'ready',
      image_url: '/t.jpg',
      medium_url: '/t-m.jpg',
      created_at: new Date().toISOString(),
      stale: false,
    })
    vi.mocked(api.post).mockResolvedValue({ status: 'pending', created_at: new Date().toISOString() })
    vi.mocked(api.delete).mockResolvedValue(undefined)
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })

    expect(await screen.findByAltText('imageAlt')).toHaveAttribute('src', '/t-m.jpg')

    fireEvent.click(screen.getByRole('button', { name: 'regenerate' }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/outfits/o1/try-on?regenerate=true')
    )
  })

  it('deletes the try-on', async () => {
    mockApi(PHOTO, {
      status: 'ready',
      image_url: '/t.jpg',
      medium_url: null,
      created_at: new Date().toISOString(),
      stale: false,
    })
    vi.mocked(api.delete).mockResolvedValue(undefined)
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    fireEvent.click(await screen.findByRole('button', { name: 'delete' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/outfits/o1/try-on'))
  })

  it('says it is taking longer and offers Retry once the server calls it retryable', async () => {
    const old = new Date(Date.now() - 6 * 60 * 1000).toISOString()
    mockApi(PHOTO, { status: 'pending', created_at: old, stale: false, retryable: false })
    const { unmount } = render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    expect(await screen.findByText('takingLonger')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'retry' })).not.toBeInTheDocument()
    unmount()

    const lost = new Date(Date.now() - 16 * 60 * 1000).toISOString()
    mockApi(PHOTO, { status: 'pending', created_at: lost, stale: false, retryable: true })
    vi.mocked(api.post).mockResolvedValue({ status: 'pending', created_at: new Date().toISOString() })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    fireEvent.click(await screen.findByRole('button', { name: 'retry' }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/outfits/o1/try-on?regenerate=true')
    )
  })

  it('does not nag about a fresh pending try-on', async () => {
    mockApi(PHOTO, { status: 'pending', created_at: new Date().toISOString(), stale: false })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    await screen.findByRole('status')
    expect(screen.queryByText('takingLonger')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'retry' })).not.toBeInTheDocument()
  })

  it('keeps showing the previous image next to the error when a regeneration failed', async () => {
    mockApi(PHOTO, {
      status: 'failed',
      error_code: 'TRY_ON_FAILED',
      image_url: '/t.jpg',
      medium_url: '/t-m.jpg',
      created_at: new Date().toISOString(),
      stale: true,
    })
    vi.mocked(api.post).mockResolvedValue({ status: 'pending', created_at: new Date().toISOString() })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    expect(await screen.findByAltText('imageAlt')).toHaveAttribute('src', '/t-m.jpg')
    expect(screen.getByRole('alert')).toHaveTextContent('errors.generic')
    expect(screen.getByRole('alert')).toHaveTextContent('keptPrevious')
    fireEvent.click(screen.getByRole('button', { name: 'regenerate' }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/outfits/o1/try-on?regenerate=true')
    )
  })

  it('shows the translated reason when the model returned no image', async () => {
    mockApi(PHOTO, {
      status: 'failed',
      error_code: 'TRY_ON_NO_IMAGE',
      image_url: null,
      medium_url: null,
      created_at: new Date().toISOString(),
      stale: false,
    })
    render(<TryOnPanel outfitId="o1" />, { wrapper: wrapperFor(ON) })
    expect(await screen.findByRole('alert')).toHaveTextContent('errors.noImage')
  })
})

describe('TryOnPhotoCard', () => {
  const OFF = { ...BASE, try_on_enabled: false }

  it('is hidden when try-on is disabled and there is no saved photo', async () => {
    mockApi(null, null)
    const { container } = render(<TryOnPhotoCard />, { wrapper: wrapperFor(OFF) })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/users/me/try-on-photo'))
    expect(container).toBeEmptyDOMElement()
  })

  it('still lets people remove a saved photo when try-on is disabled, and nothing else', async () => {
    mockApi(PHOTO, null)
    vi.mocked(api.delete).mockResolvedValue(undefined)
    render(<TryOnPhotoCard />, { wrapper: wrapperFor(OFF) })
    expect(await screen.findByText('disabledNotice')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'upload' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'replace' })).not.toBeInTheDocument()
    expect(screen.queryByText('privacy')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'remove' }))
    fireEvent.click(await screen.findByRole('button', { name: 'removeConfirm.confirm' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/users/me/try-on-photo'))
  })

  it('does not read the photo while the features call is still loading', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const { container } = render(<TryOnPhotoCard />, { wrapper: wrapperFor() })
    expect(container).toBeEmptyDOMElement()
  })

  it('cannot choose or replace a photo before the photo query has resolved', async () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const { getByTestId } = render(<TryOnPhotoCard />, { wrapper: wrapperFor(ON) })
    expect(screen.getByRole('button', { name: 'upload' })).toBeDisabled()
    // Even a file that arrives anyway (drop, extension) must not skip the confirmation.
    const file = new File(['x'], 'me.jpg', { type: 'image/jpeg' })
    fireEvent.change(getByTestId('try-on-photo-input'), { target: { files: [file] } })
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('shows the upload action and the privacy line when enabled', async () => {
    mockApi(null, null)
    const { container } = render(<TryOnPhotoCard />, { wrapper: wrapperFor(ON) })
    expect(container.querySelector('#try-on-photo')).not.toBeNull()
    expect(await screen.findByRole('button', { name: 'upload' })).toBeInTheDocument()
    expect(screen.getByText('privacy')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'remove' })).not.toBeInTheDocument()
  })

  it('confirms before removing the photo', async () => {
    mockApi(PHOTO, null)
    vi.mocked(api.delete).mockResolvedValue(undefined)
    render(<TryOnPhotoCard />, { wrapper: wrapperFor(ON) })
    fireEvent.click(await screen.findByRole('button', { name: 'remove' }))
    expect(api.delete).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: 'removeConfirm.confirm' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/users/me/try-on-photo'))
  })
})
