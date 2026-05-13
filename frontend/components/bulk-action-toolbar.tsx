'use client';

import { X, Trash2, RefreshCw, Loader2, CheckSquare, Square, MinusSquare, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useTranslations } from 'next-intl';

export interface BulkSelection {
  mode: 'none' | 'some' | 'all';
  selectedIds: Set<string>;    // Used when mode is 'some'
  excludedIds: Set<string>;    // Used when mode is 'all'
}

interface BulkActionToolbarProps {
  selection: BulkSelection;
  totalItems: number;
  pageItems: number;
  onSelectAll: () => void;
  onClear: () => void;
  onDelete: () => void;
  onReanalyze: () => void;
  isDeleting?: boolean;
  isReanalyzing?: boolean;
  // Pagination props
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function BulkActionToolbar({
  selection,
  totalItems,
  pageItems,
  onSelectAll,
  onClear,
  onDelete,
  onReanalyze,
  isDeleting = false,
  isReanalyzing = false,
  page,
  pageSize,
  onPageChange,
}: BulkActionToolbarProps) {
  const t = useTranslations('shared.bulkAction');
  // Calculate selected count
  const selectedCount = selection.mode === 'all'
    ? totalItems - selection.excludedIds.size
    : selection.selectedIds.size;

  // Determine checkbox state
  const isAllSelected = selection.mode === 'all' && selection.excludedIds.size === 0;
  const isPartiallySelected = selection.mode === 'all'
    ? selection.excludedIds.size > 0
    : selection.selectedIds.size > 0 && selection.selectedIds.size < pageItems;
  const hasSelection = selectedCount > 0;

  // Pagination
  const totalPages = Math.ceil(totalItems / pageSize);
  const showPagination = totalPages > 1;

  return (
    <div className="fixed bottom-20 sm:bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 sm:gap-3 bg-background border rounded-lg shadow-lg px-2 sm:px-4 py-2 sm:py-3 max-w-[calc(100vw-1rem)]">
      {/* Select All Checkbox */}
      <div
        className="flex items-center gap-1 sm:gap-2 cursor-pointer shrink-0"
        onClick={onSelectAll}
      >
        {isAllSelected ? (
          <CheckSquare className="h-5 w-5 text-primary" />
        ) : isPartiallySelected ? (
          <MinusSquare className="h-5 w-5 text-primary" />
        ) : (
          <Square className="h-5 w-5 text-muted-foreground" />
        )}
        <span className="text-sm font-medium whitespace-nowrap hidden sm:inline">
          {isAllSelected ? t('all') : t('selectAll')}
        </span>
      </div>

      <div className="h-4 w-px bg-border shrink-0" />

      <span className="text-sm text-muted-foreground whitespace-nowrap shrink-0">
        {selectedCount === 0 ? (
          <span className="hidden sm:inline">{t('noneSelected')}</span>
        ) : selection.mode === 'all' && selection.excludedIds.size > 0 ? (
          <>
            <span className="sm:hidden">{totalItems - selection.excludedIds.size}</span>
            <span className="hidden sm:inline">{t('allExcept', { count: selection.excludedIds.size })}</span>
          </>
        ) : selection.mode === 'all' ? (
          <>
            <span className="sm:hidden">All ({totalItems})</span>
            <span className="hidden sm:inline">{t('allSelected', { count: totalItems })}</span>
          </>
        ) : (
          <>
            <span className="sm:hidden">{selectedCount}</span>
            <span className="hidden sm:inline">{t('selected', { count: selectedCount })}</span>
          </>
        )}
      </span>

      {hasSelection && (
        <>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClear}
            className="text-muted-foreground h-8 w-8 shrink-0"
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </Button>
          <div className="h-4 w-px bg-border shrink-0" />
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={onReanalyze}
            disabled={isReanalyzing}
            aria-label="Re-analyze"
          >
            {isReanalyzing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="icon" className="h-8 w-8 shrink-0" disabled={isDeleting} aria-label="Delete">
                {isDeleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t('deleteConfirm.title', { count: selection.mode === 'all' && selection.excludedIds.size === 0 ? totalItems : selectedCount })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t('deleteConfirm.description')}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={onDelete}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </>
      )}

      {/* Pagination */}
      {showPagination && (
        <>
          <div className="h-4 w-px bg-border shrink-0" />
          <div className="flex items-center gap-0.5 sm:gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 hidden sm:flex"
              disabled={page === 1}
              onClick={() => onPageChange(1)}
              aria-label="First page"
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page === 1}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="px-1 sm:px-2 text-sm text-muted-foreground whitespace-nowrap">
              {page}/{totalPages}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 hidden sm:flex"
              disabled={page >= totalPages}
              onClick={() => onPageChange(totalPages)}
              aria-label="Last page"
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
