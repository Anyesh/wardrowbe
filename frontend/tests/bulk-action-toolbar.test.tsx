import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BulkActionToolbar, type BulkSelection } from '@/components/bulk-action-toolbar'

function renderToolbar(selection: BulkSelection, totalItems: number, pageItems: number) {
  render(
    <BulkActionToolbar
      selection={selection}
      totalItems={totalItems}
      pageItems={pageItems}
      onSelectAll={vi.fn()}
      onSelectAllMatching={vi.fn()}
      onClear={vi.fn()}
      onDelete={vi.fn()}
      variant="outfits"
    />,
  )
}

const ids = (n: number) => new Set(Array.from({ length: n }, (_, i) => `o${i}`))
const none = new Set<string>()

describe('BulkActionToolbar select-all label', () => {
  it.each([
    ['every loaded row of a longer list', { mode: 'some', selectedIds: ids(20), excludedIds: none }, 50, 20, 'selectAll', true],
    ['every row when everything is loaded', { mode: 'some', selectedIds: ids(20), excludedIds: none }, 20, 20, 'bulkActions.all', false],
    ['all matching', { mode: 'all', selectedIds: none, excludedIds: none }, 50, 20, 'bulkActions.all', false],
    ['all matching but one', { mode: 'all', selectedIds: none, excludedIds: ids(1) }, 50, 20, 'selectAll', false],
  ] as const)('with %s selected', (_, selection, total, page, label, offersMatching) => {
    renderToolbar(selection as BulkSelection, total, page)

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.queryByText('bulkActions.selectAllMatching') !== null).toBe(offersMatching)
  })
})
