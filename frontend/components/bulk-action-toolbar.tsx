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

export type BulkDeleteVariant = 'items' | 'outfits';

interface BulkActionToolbarProps {
  selection: BulkSelection;
  totalItems: number;
  pageItems: number;
  onSelectAll: () => void;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onDelete: () => void;
  onReanalyze?: () => void;
  isDeleting?: boolean;
  isReanalyzing?: boolean;
  variant?: BulkDeleteVariant;
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
  onSelectAllMatching,
  onClear,
  onDelete,
  onReanalyze,
  isDeleting = false,
  isReanalyzing = false,
  variant = 'items',
  page,
  pageSize,
  onPageChange,
}: BulkActionToolbarProps) {
  const t = useTranslations('common');
  const tWardrobe = useTranslations('wardrobe');
  const tOutfits = useTranslations('outfits');
  // Each variant carries a whole delete sentence so that gendered and case-inflected
  // languages are never handed a bare noun to splice into English grammar.
  const tDelete = variant === 'outfits' ? tOutfits : tWardrobe;

  const selectedCount = selection.mode === 'all'
    ? totalItems - selection.excludedIds.size
    : selection.selectedIds.size;

  // Determine checkbox state
  const isAllSelected =
    (selection.mode === 'all' && selection.excludedIds.size === 0) ||
    (selection.mode === 'some' && selection.selectedIds.size === pageItems && pageItems > 0);
  const isPartiallySelected = selection.mode === 'all'
    ? selection.excludedIds.size > 0
    : selection.selectedIds.size > 0 && selection.selectedIds.size < pageItems;
  const hasSelection = selectedCount > 0;
  const canSelectAllMatching =
    selection.mode === 'some' && selection.selectedIds.size === pageItems && pageItems > 0 && pageItems < totalItems;

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
          {isAllSelected ? t('bulkActions.all') : t('selectAll')}
        </span>
      </div>

      <div className="h-4 w-px bg-border shrink-0" />

      <span className="text-sm text-muted-foreground whitespace-nowrap shrink-0">
        {selectedCount === 0 ? (
          <span className="hidden sm:inline">{t('bulkActions.noneSelected')}</span>
        ) : selection.mode === 'all' && selection.excludedIds.size > 0 ? (
          <>
            <span className="sm:hidden">{totalItems - selection.excludedIds.size}</span>
            <span className="hidden sm:inline">{t('bulkActions.allExcept', { count: selection.excludedIds.size })}</span>
          </>
        ) : selection.mode === 'all' ? (
          <>
            <span className="sm:hidden">{t('bulkActions.allShort', { count: totalItems })}</span>
            <span className="hidden sm:inline">{t('bulkActions.allSelected', { count: totalItems })}</span>
          </>
        ) : (
          <>
            <span className="sm:hidden">{selectedCount}</span>
            <span className="hidden sm:inline">{t('selected', { count: selectedCount })}</span>
          </>
        )}
      </span>

      {canSelectAllMatching && (
        <Button
          variant="link"
          size="sm"
          className="h-8 px-0 text-xs shrink-0 hidden sm:inline-flex"
          onClick={onSelectAllMatching}
        >
          {t('bulkActions.selectAllMatching', { count: totalItems })}
        </Button>
      )}

      {hasSelection && (
        <>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClear}
            className="text-muted-foreground h-8 w-8 shrink-0"
            aria-label={t('bulkActions.clearSelection')}
          >
            <X className="h-4 w-4" />
          </Button>
          <div className="h-4 w-px bg-border shrink-0" />
          {onReanalyze && (
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={onReanalyze}
              disabled={isReanalyzing}
              aria-label={t('bulkActions.reanalyze')}
            >
              {isReanalyzing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="icon" className="h-8 w-8 shrink-0" disabled={isDeleting} aria-label={t('delete')}>
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
                  {selection.mode === 'all' && selection.excludedIds.size === 0
                    ? tDelete('bulkDelete.confirmTitleAll', { count: totalItems })
                    : tDelete('bulkDelete.confirmTitle', { count: selectedCount })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {tDelete('bulkDelete.confirmDescription')}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={onDelete}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {t('delete')}
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
              aria-label={t('firstPage')}
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page === 1}
              onClick={() => onPageChange(page - 1)}
              aria-label={t('previousPage')}
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
              aria-label={t('nextPage')}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 hidden sm:flex"
              disabled={page >= totalPages}
              onClick={() => onPageChange(totalPages)}
              aria-label={t('lastPage')}
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
