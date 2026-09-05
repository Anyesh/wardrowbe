import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { render, screen, within, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { AnalysisQueuePanel } from '@/components/analysis-queue-panel'
import type { TaggingProgress } from '@/lib/types'

// next-intl is mocked globally to echo the key, so every string the panel
// renders shows up as a key path. That makes the panel assertions readable and
// lets one test check every key it emits against the English catalog, which is
// the only thing that catches a key the panel invents but nobody translated.
function flatten(obj: Record<string, unknown>, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flatten(v as Record<string, unknown>, path))
    } else {
      out[path] = v
    }
  }
  return out
}

const EN = (() => {
  const dir = resolve(__dirname, '..', 'messages', 'en')
  const flat: Record<string, unknown> = {}
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const ns = file.slice(0, -5)
    for (const [k, v] of Object.entries(flatten(JSON.parse(readFileSync(join(dir, file), 'utf8'))))) {
      flat[`${ns}.${k}`] = v
    }
  }
  return flat
})()

function progress(overrides: Partial<TaggingProgress> = {}): TaggingProgress {
  return {
    processing: 0,
    queued: 0,
    analyzing: 0,
    failed: 0,
    completed: 0,
    total: 0,
    batch_total: 0,
    batch_completed: 0,
    batch_failed: 0,
    current: [],
    recent: [],
    failures: [],
    avg_duration_seconds: null,
    eta_seconds: null,
    concurrency: 1,
    ...overrides,
  }
}

function renderPanel(p?: TaggingProgress, onRetry = vi.fn()) {
  render(
    <AnalysisQueuePanel open onOpenChange={vi.fn()} progress={p} onRetry={onRetry} />
  )
  return onRetry
}

describe('AnalysisQueuePanel', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-09-04T10:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('says the queue is empty when nothing has run', () => {
    renderPanel(progress())
    expect(screen.getByText('idle')).toBeInTheDocument()
    expect(screen.queryByText('nowAnalyzing')).not.toBeInTheDocument()
  })

  it('shows a queued run as waiting with no estimate yet', () => {
    renderPanel(progress({ processing: 90, queued: 90, batch_total: 90 }))

    expect(screen.getByText('batchProgress')).toBeInTheDocument()
    expect(screen.getByText('waitingToStart')).toBeInTheDocument()
    expect(screen.queryByText('nowAnalyzing')).not.toBeInTheDocument()
  })

  it('lists the item being analyzed with its live elapsed time', () => {
    renderPanel(
      progress({
        processing: 3,
        analyzing: 1,
        queued: 2,
        batch_total: 5,
        batch_completed: 2,
        current: [
          {
            item_id: 'a',
            name: 'Blue oxford',
            type: 'shirt',
            image_url: '/img/a.jpg',
            started_at: '2026-09-04T09:59:18.000Z',
          },
        ],
      })
    )

    expect(screen.getByText('nowAnalyzing')).toBeInTheDocument()
    expect(screen.getByText('Blue oxford')).toBeInTheDocument()
    expect(screen.getByText('42s')).toBeInTheDocument()
  })

  it('shows completed durations and both derived estimates', () => {
    renderPanel(
      progress({
        processing: 2,
        queued: 2,
        batch_total: 5,
        batch_completed: 3,
        avg_duration_seconds: 40,
        eta_seconds: 80,
        recent: [
          {
            item_id: 'r1',
            name: 'Grey tee',
            type: 't-shirt',
            duration_seconds: 42,
            completed_at: '2026-09-04T09:59:00.000Z',
          },
        ],
      })
    )

    expect(screen.getByText('recentlyFinished')).toBeInTheDocument()
    expect(screen.getByText('42s')).toBeInTheDocument()
    expect(screen.getByText('40s')).toBeInTheDocument()
    expect(screen.getByText('1m 20s')).toBeInTheDocument()
  })

  it('shows each failure with its reason and retries the right item', () => {
    const onRetry = renderPanel(
      progress({
        failed: 1,
        batch_total: 3,
        batch_completed: 2,
        batch_failed: 1,
        failures: [
          {
            item_id: 'broken-1',
            name: 'Red scarf',
            type: 'scarf',
            error: 'model qwen2.5vl not found',
            failed_at: '2026-09-04T09:58:00.000Z',
          },
        ],
      })
    )

    expect(screen.getByText('model qwen2.5vl not found')).toBeInTheDocument()
    expect(screen.getByText('batchFailed')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith('broken-1')
  })

  it('drops the time-left estimate once nothing is left to analyze', () => {
    renderPanel(
      progress({
        avg_duration_seconds: 12,
        recent: [
          {
            item_id: 'r1',
            name: 'Grey tee',
            type: 't-shirt',
            duration_seconds: 12,
            completed_at: '2026-09-04T09:59:00.000Z',
          },
        ],
      })
    )

    expect(screen.getByText('averageLabel')).toBeInTheDocument()
    expect(screen.queryByText('remainingLabel')).not.toBeInTheDocument()
  })

  it('falls back to a translated label when an item has no name yet', () => {
    renderPanel(
      progress({
        processing: 1,
        analyzing: 1,
        batch_total: 1,
        current: [
          {
            item_id: 'fresh',
            name: null,
            // Freshly uploaded items carry `unknown`, which has no entry in
            // constants.types; translating it blindly renders a key path.
            type: 'unknown',
            image_url: null,
            started_at: '2026-09-04T09:59:55.000Z',
          },
        ],
        recent: [
          {
            item_id: 'tagged',
            name: null,
            type: 'jacket',
            duration_seconds: 10,
            completed_at: '2026-09-04T09:59:00.000Z',
          },
        ],
      })
    )

    expect(screen.getByText('unnamedItem')).toBeInTheDocument()
    expect(screen.getByText('jacket')).toBeInTheDocument()
  })

  it('renders no string the English catalog cannot resolve', () => {
    renderPanel(
      progress({
        processing: 2,
        analyzing: 1,
        queued: 1,
        failed: 1,
        batch_total: 5,
        batch_completed: 1,
        batch_failed: 1,
        avg_duration_seconds: 30,
        eta_seconds: 60,
        concurrency: 2,
        current: [
          {
            item_id: 'a',
            name: 'Blue oxford',
            type: 'shirt',
            image_url: '/img/a.jpg',
            started_at: '2026-09-04T09:59:30.000Z',
          },
        ],
        recent: [
          {
            item_id: 'b',
            name: 'Grey tee',
            type: 't-shirt',
            duration_seconds: null,
            completed_at: '2026-09-04T09:59:00.000Z',
          },
        ],
        failures: [
          {
            item_id: 'c',
            name: 'Red scarf',
            type: 'scarf',
            error: null,
            failed_at: '2026-09-04T09:58:00.000Z',
          },
        ],
      })
    )

    const dialog = screen.getByRole('dialog')
    const rendered = new Set(
      Array.from(dialog.querySelectorAll('*'))
        .filter((el) => el.tagName !== 'STYLE' && el.tagName !== 'SCRIPT')
        .flatMap((el) => Array.from(el.childNodes))
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => (n.textContent ?? '').trim())
        .filter(Boolean)
    )

    const literals = new Set([
      'Blue oxford',
      'Grey tee',
      'Red scarf',
      '30s',
      '1m 0s',
      'shirt',
      't-shirt',
      'scarf',
      // The shared dialog primitive hardcodes its own close label; that gap
      // predates this panel and lives in components/ui/dialog.tsx.
      'Close',
    ])
    const keys = Array.from(rendered).filter(
      (text) => !literals.has(text) && !/^\d+[sm]/.test(text)
    )

    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) {
      expect(
        EN[`wardrobe.ai.queue.${key}`] ?? EN[`common.${key}`],
        `no English message for "${key}"`
      ).toBeDefined()
    }
  })

  it('reports how many items the instance analyzes at once', () => {
    renderPanel(progress({ concurrency: 4 }))
    const footer = screen.getByText('concurrencyLink').parentElement
    expect(within(footer as HTMLElement).getByText('concurrency')).toBeInTheDocument()
  })
})
