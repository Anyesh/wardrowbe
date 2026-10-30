import { describe, expect, it } from 'vitest'
import { clampBox, MIN_BOX_SIDE, moveBox, newBox, resizeBox, type Box } from '@/lib/split-boxes'

const box: Box = { left: 0.2, top: 0.2, width: 0.4, height: 0.5 }

describe('clampBox', () => {
  it('leaves a box inside the photo alone', () => {
    expect(clampBox(box)).toEqual(box)
  })

  it('pulls a box back inside the photo', () => {
    expect(clampBox({ left: 0.9, top: -0.2, width: 0.4, height: 0.3 })).toEqual({
      left: 0.6,
      top: 0,
      width: 0.4,
      height: 0.3,
    })
  })

  it('stops a box shrinking below the minimum and growing past the photo', () => {
    const tiny = clampBox({ left: 0, top: 0, width: 0, height: 0.001 })
    const huge = clampBox({ left: 0.5, top: 0.5, width: 3, height: 3 })

    expect(tiny.width).toBe(MIN_BOX_SIDE)
    expect(tiny.height).toBe(MIN_BOX_SIDE)
    expect(huge).toEqual({ left: 0, top: 0, width: 1, height: 1 })
  })
})

describe('moveBox', () => {
  it('moves by the given fractions', () => {
    const moved = moveBox(box, 0.1, -0.1)

    expect(moved.left).toBeCloseTo(0.3)
    expect(moved.top).toBeCloseTo(0.1)
    expect(moved.width).toBe(0.4)
    expect(moved.height).toBe(0.5)
  })

  it('stops at every edge without changing size', () => {
    expect(moveBox(box, -5, -5)).toEqual({ left: 0, top: 0, width: 0.4, height: 0.5 })
    expect(moveBox(box, 5, 5)).toEqual({ left: 0.6, top: 0.5, width: 0.4, height: 0.5 })
  })
})

describe('resizeBox', () => {
  it('moves one corner and keeps the opposite corner fixed', () => {
    const resized = resizeBox(box, 'se', 0.1, 0.1)

    expect(resized.left).toBeCloseTo(0.2)
    expect(resized.top).toBeCloseTo(0.2)
    expect(resized.width).toBeCloseTo(0.5)
    expect(resized.height).toBeCloseTo(0.6)

    const nw = resizeBox(box, 'nw', 0.1, 0.1)
    expect(nw.left + nw.width).toBeCloseTo(0.6)
    expect(nw.top + nw.height).toBeCloseTo(0.7)
    expect(nw.width).toBeCloseTo(0.3)
  })

  it.each(['nw', 'ne', 'sw', 'se'] as const)('%s never inverts or shrinks below the minimum', (handle) => {
    const squashed = resizeBox(box, handle, handle.includes('w') ? 5 : -5, handle.includes('n') ? 5 : -5)

    expect(squashed.width).toBeGreaterThanOrEqual(MIN_BOX_SIDE - 1e-9)
    expect(squashed.height).toBeGreaterThanOrEqual(MIN_BOX_SIDE - 1e-9)
  })

  it.each(['nw', 'ne', 'sw', 'se'] as const)('%s never leaves the photo', (handle) => {
    const out = resizeBox(box, handle, handle.includes('w') ? -5 : 5, handle.includes('n') ? -5 : 5)

    expect(out.left).toBeGreaterThanOrEqual(0)
    expect(out.top).toBeGreaterThanOrEqual(0)
    expect(out.left + out.width).toBeLessThanOrEqual(1 + 1e-9)
    expect(out.top + out.height).toBeLessThanOrEqual(1 + 1e-9)
  })
})

describe('newBox', () => {
  it('starts centred and inside the photo, offset from the earlier ones', () => {
    const first = newBox(0)
    const second = newBox(1)

    expect(first).toEqual({ left: 0.3, top: 0.3, width: 0.4, height: 0.4 })
    expect(second.left).toBeGreaterThan(first.left)
    for (let n = 0; n < 12; n++) {
      const b = newBox(n)
      expect(b.left + b.width).toBeLessThanOrEqual(1 + 1e-9)
      expect(b.top + b.height).toBeLessThanOrEqual(1 + 1e-9)
    }
  })
})
