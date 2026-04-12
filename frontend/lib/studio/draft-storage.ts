const DRAFT_KEY = 'studio_draft_v1';
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

export interface StudioDraft {
  items: string[];
  name: string;
  occasion: string | null;
  timestamp: number;
}

export function saveDraft(
  draft: Omit<StudioDraft, 'timestamp'>
): void {
  if (typeof window === 'undefined') return;
  try {
    const payload: StudioDraft = { ...draft, timestamp: Date.now() };
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  } catch {
    // localStorage full or disabled
  }
}

export function loadDraft(): StudioDraft | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as StudioDraft;
    if (!draft || typeof draft.timestamp !== 'number') return null;
    if (Date.now() - draft.timestamp > DRAFT_TTL_MS) {
      window.localStorage.removeItem(DRAFT_KEY);
      return null;
    }
    return draft;
  } catch {
    return null;
  }
}

export function clearDraft(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // noop
  }
}
