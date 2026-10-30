import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitPhotoDialog } from '@/components/split-photo-dialog'
import { ApiError, api } from '@/lib/api'
import { createQueryClient } from '@/lib/query-client'
import { MAX_BOXES } from '@/lib/split-boxes'

vi.mock('@/lib/api', async () => ({
  ...(await vi.importActual('@/lib/api')),
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('sonner', () => ({ toast }))

const garment = (left: number, top: number, type = 'shirt') => ({
  type,
  colors: [],
  left,
  top,
  width: 0.3,
  height: 0.3,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

function renderDialog(props: Partial<React.ComponentProps<typeof SplitPhotoDialog>> = {}, strict = false) {
  const onClose = vi.fn()
  const onDone = vi.fn()
  // The app's client, so the global error toast is live and a second toast would show.
  const client = createQueryClient()
  const dialog = (
    <QueryClientProvider client={client}>
      <SplitPhotoDialog itemId="item-1" imageUrl="/p.jpg" open onClose={onClose} onDone={onDone} {...props} />
    </QueryClientProvider>
  )
  render(strict ? <StrictMode>{dialog}</StrictMode> : dialog)
  return { onClose, onDone }
}

beforeEach(() => {
  vi.mocked(api.post).mockReset()
  toast.success.mockReset()
  toast.error.mockReset()
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.getBoundingClientRect = () =>
    ({ x: 0, y: 0, left: 0, top: 0, right: 400, bottom: 600, width: 400, height: 600, toJSON: () => ({}) }) as DOMRect
})

describe('SplitPhotoDialog', () => {
  it.each([
    { name: 'plain', strict: false, drawn: 0, total: 2 },
    { name: 'strict mode', strict: true, drawn: 0, total: 2 },
    { name: 'a box drawn while detecting', strict: true, drawn: 1, total: 3 },
    { name: 'boxes drawn up to the limit while detecting', strict: true, drawn: MAX_BOXES - 1, total: MAX_BOXES },
  ])('asks the AI once and adds a numbered box per garment ($name)', async ({ strict, drawn, total }) => {
    const detection = deferred<{ garments: ReturnType<typeof garment>[] }>()
    vi.mocked(api.post).mockReturnValueOnce(detection.promise)

    renderDialog({}, strict)

    expect(await screen.findByText('detecting')).toBeInTheDocument()
    const add = screen.getByRole('button', { name: 'addBox' })
    if (drawn > 0) {
      expect(add).toBeEnabled()
      for (let i = 0; i < drawn; i++) fireEvent.click(add)
      expect(screen.getByTestId(`split-box-${drawn}`)).toBeInTheDocument()
    }

    detection.resolve({ garments: [garment(0.1, 0.1), garment(0.5, 0.5, 'jeans')] })

    expect(await screen.findByTestId(`split-box-${total}`)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('detecting')).not.toBeInTheDocument())
    expect(screen.queryByTestId(`split-box-${total + 1}`)).not.toBeInTheDocument()
    expect(screen.getByTestId(`split-box-${drawn + 1}`).style.left).toBe('10%')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/items/item-1/detect-garments')
    expect(screen.getByRole('button', { name: 'create' })).toBeEnabled()
    if (total === MAX_BOXES) expect(add).toBeDisabled()
  })

  it('positions each box as a percentage of the photo', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ garments: [garment(0.1, 0.2)] })

    renderDialog()

    const box = await screen.findByTestId('split-box-1')
    expect(box.style.left).toBe('10%')
    expect(box.style.top).toBe('20%')
    expect(box.style.width).toBe('30%')
  })

  it('removes a box', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ garments: [garment(0.1, 0.1), garment(0.5, 0.5)] })
    renderDialog()
    await screen.findByTestId('split-box-2')

    // the test translator returns the key, so both remove buttons share a name: take the second
    fireEvent.click(screen.getAllByRole('button', { name: 'removeBox' })[1])

    await waitFor(() => expect(screen.queryByTestId('split-box-2')).not.toBeInTheDocument())
    expect(screen.getByTestId('split-box-1')).toBeInTheDocument()
  })

  it('adds a box by hand, up to the limit', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ garments: [] })
    renderDialog()
    expect(await screen.findByText('noneFound')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'create' })).toBeDisabled()

    const add = screen.getByRole('button', { name: 'addBox' })
    for (let i = 0; i < MAX_BOXES; i++) fireEvent.click(add)

    expect(screen.getByTestId(`split-box-${MAX_BOXES}`)).toBeInTheDocument()
    expect(add).toBeDisabled()
    expect(screen.getByRole('button', { name: 'create' })).toBeEnabled()
  })

  it('moves a box when it is dragged', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ garments: [garment(0.1, 0.1)] })
    renderDialog()
    const box = await screen.findByTestId('split-box-1')

    fireEvent.pointerDown(box, { clientX: 100, clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(box, { clientX: 140, clientY: 160, pointerId: 1 })
    fireEvent.pointerUp(box, { pointerId: 1 })

    // 40px of 400 across, 60px of 600 down: a tenth each way
    expect(parseFloat(box.style.left)).toBeCloseTo(20)
    expect(parseFloat(box.style.top)).toBeCloseTo(20)
    expect(parseFloat(box.style.width)).toBeCloseTo(30)
  })

  it('resizes a box from a corner without moving the opposite corner', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ garments: [garment(0.1, 0.1)] })
    renderDialog()
    const box = await screen.findByTestId('split-box-1')
    const handle = box.querySelector('[data-handle="se"]') as HTMLElement

    fireEvent.pointerDown(handle, { clientX: 160, clientY: 240, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 200, clientY: 300, pointerId: 1 })
    fireEvent.pointerUp(handle, { pointerId: 1 })

    expect(parseFloat(box.style.left)).toBeCloseTo(10)
    expect(parseFloat(box.style.top)).toBeCloseTo(10)
    expect(parseFloat(box.style.width)).toBeCloseTo(40)
    expect(parseFloat(box.style.height)).toBeCloseTo(40)
  })

  it('creates the items from the boxes as they are now, then closes', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ garments: [garment(0.1, 0.1), garment(0.5, 0.5)] })
      .mockResolvedValueOnce({ source_id: 'item-1', item_ids: ['a', 'b'] })
    const { onClose, onDone } = renderDialog()
    await screen.findByTestId('split-box-2')

    fireEvent.click(screen.getByRole('button', { name: 'create' }))

    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
    expect(api.post).toHaveBeenLastCalledWith('/items/item-1/split', {
      boxes: [
        { left: 0.1, top: 0.1, width: 0.3, height: 0.3 },
        { left: 0.5, top: 0.5, width: 0.3, height: 0.3 },
      ],
    })
    expect(toast.success).toHaveBeenCalled()
  })

  it('keeps the dialog open and says so when creating fails', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ garments: [garment(0.1, 0.1)] })
      .mockRejectedValueOnce(new Error('boom'))
    const { onClose, onDone } = renderDialog()
    await screen.findByTestId('split-box-1')

    fireEvent.click(screen.getByRole('button', { name: 'create' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
    expect(screen.getByTestId('split-box-1')).toBeInTheDocument()
  })

  it.each([
    {
      name: 'an unreachable AI',
      error: new ApiError('AI service is unreachable', 502, {
        detail: { message: 'AI service is unreachable', error_code: 'AI_UNREACHABLE' },
      }),
      text: 'detectFailed',
    },
  ])('shows a detection failure inline, without a toast ($name)', async ({ error, text }) => {
    vi.mocked(api.post).mockRejectedValueOnce(error)
    renderDialog()

    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(toast.error).not.toHaveBeenCalled()
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('offers a retry when the AI cannot be reached, and keeps boxes drawn by hand', async () => {
    const retry = deferred<{ garments: ReturnType<typeof garment>[] }>()
    vi.mocked(api.post).mockRejectedValueOnce(new Error('503')).mockReturnValueOnce(retry.promise)
    renderDialog()

    expect(await screen.findByText('detectFailed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'addBox' }))
    expect(screen.getByTestId('split-box-1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'retry' }))

    expect(await screen.findByText('detecting')).toBeInTheDocument()
    expect(screen.queryByText('detectFailed')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'retry' })).not.toBeInTheDocument()
    expect(api.post).toHaveBeenCalledTimes(2)

    retry.resolve({ garments: [garment(0.5, 0.5)] })

    expect(await screen.findByTestId('split-box-2')).toBeInTheDocument()
    expect(screen.getByTestId('split-box-1').style.left).toBe('30%')
    expect(screen.getByTestId('split-box-2').style.left).toBe('50%')
  })
})
