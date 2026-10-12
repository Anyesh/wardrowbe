// Must match DEFAULT_PAGE_SIZE and MAX_PAGE_SIZE in backend/app/api/pagination.py.
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;

// Divisible by every grid column count (2, 3, 4, 6) so that full pages end on a full row.
export const GRID_PAGE_SIZE = 24;
