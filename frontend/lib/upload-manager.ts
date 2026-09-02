import type { QueryClient } from '@tanstack/react-query';
import { getAccessToken } from '@/lib/api';
import {
  getPendingUploads,
  markUploading,
  markDone,
  markRetryable,
  markTerminal,
  markPendingForRetry,
  getStoragePersisted,
  purgeAbandoned,
  dismiss as dismissRecord,
  type QueuedUpload,
} from '@/lib/upload-queue';
import { mergeBulkUploadResponses, type BulkUploadResponse } from '@/lib/hooks/use-items';

// A flat file-count chunk (previously 20) doesn't account for file size: 20
// modern phone photos routinely exceed nginx's default 50MB
// client_max_body_size, producing a 413 that isn't recognized as the known
// "Maximum N images" case (that regex only matches the backend's own
// count-based 400), so the whole chunk lands in retry backoff. Chunking by a
// byte budget well under that cap avoids the 413 in the common case and
// shrinks the retry/close-window blast radius regardless.
const BULK_UPLOAD_CHUNK_SIZE = 8;
const BULK_UPLOAD_MAX_BYTES = 15 * 1024 * 1024;
const MAX_ATTEMPTS = 5;
const RETRY_BACKOFF_BASE_MS = 5000;
const BULK_LIMIT_ERROR = /^Maximum (\d+) images per bulk upload$/;

class BulkLimitExceededError extends Error {
  constructor(public readonly limit: number) {
    super(`Server bulk upload limit is ${limit}`);
  }
}

// The server's configured max_bulk_upload_count (admin-tunable, self-hosted)
// isn't exposed to the client, so a chunk sized for the default of 20 gets
// the WHOLE request rejected - not just the excess files - on an instance
// where an admin lowered it below 20. Cached at module scope so once the
// real limit is learned, later drain passes stop re-discovering it via a
// failed request on every pass.
let effectiveChunkSize = BULK_UPLOAD_CHUNK_SIZE;

export interface TerminalRecord {
  id: string;
  filename: string;
  size: number;
  lastError: string | null;
}

export interface DrainState {
  draining: boolean;
  remaining: number;
  terminalRecords: TerminalRecord[];
  storagePersisted: boolean | null;
}

type Listener = (state: DrainState) => void;

let queryClient: QueryClient | null = null;
let isDraining = false;
const listeners = new Set<Listener>();
let beforeUnloadRegistered = false;

function onBeforeUnload(e: BeforeUnloadEvent) {
  // preventDefault() alone doesn't surface the confirmation dialog in every
  // browser - some still require the legacy returnValue assignment.
  e.preventDefault();
  e.returnValue = '';
}

async function computeState(): Promise<DrainState> {
  const records = await getPendingUploads();
  const remaining = records.filter((r) => r.status !== 'failed').length;
  const terminalRecords: TerminalRecord[] = records
    .filter((r) => r.terminal)
    .map((r) => ({ id: r.id, filename: r.filename, size: r.size, lastError: r.lastError }));
  const storagePersisted = await getStoragePersisted();

  if (typeof window !== 'undefined') {
    if (remaining > 0 && !beforeUnloadRegistered) {
      window.addEventListener('beforeunload', onBeforeUnload);
      beforeUnloadRegistered = true;
    } else if (remaining === 0 && beforeUnloadRegistered) {
      window.removeEventListener('beforeunload', onBeforeUnload);
      beforeUnloadRegistered = false;
    }
  }

  return { draining: isDraining, remaining, terminalRecords, storagePersisted };
}

async function emit(): Promise<void> {
  const state = await computeState();
  listeners.forEach((listener) => listener(state));
}

export function init(client: QueryClient): void {
  queryClient = client;
  effectiveChunkSize = BULK_UPLOAD_CHUNK_SIZE;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function getState(): Promise<DrainState> {
  return computeState();
}

async function uploadChunk(chunk: QueuedUpload[]): Promise<BulkUploadResponse> {
  const formData = new FormData();
  chunk.forEach((record) => formData.append('images', record.file, record.filename));
  formData.append('skip_ai', String(chunk[0]?.skipAi ?? false));
  chunk.forEach((record) => formData.append('upload_keys', record.id));

  const token = getAccessToken();
  const response = await fetch('/api/v1/items/bulk', {
    method: 'POST',
    body: formData,
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  if (!response.ok) {
    if (response.status === 400) {
      const body = await response.json().catch(() => null);
      const match =
        typeof body?.detail === 'string' ? body.detail.match(BULK_LIMIT_ERROR) : null;
      if (match) {
        throw new BulkLimitExceededError(Number(match[1]));
      }
    }
    throw new Error(`Bulk upload request failed with status ${response.status}`);
  }
  return response.json();
}

async function uploadChunkWithinServerLimit(chunk: QueuedUpload[]): Promise<BulkUploadResponse> {
  try {
    return await uploadChunk(chunk);
  } catch (error) {
    if (error instanceof BulkLimitExceededError && error.limit > 0 && error.limit < chunk.length) {
      effectiveChunkSize = Math.min(effectiveChunkSize, error.limit);
      const responses: BulkUploadResponse[] = [];
      for (let i = 0; i < chunk.length; i += error.limit) {
        responses.push(await uploadChunkWithinServerLimit(chunk.slice(i, i + error.limit)));
      }
      return mergeBulkUploadResponses(responses);
    }
    throw error;
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Upload failed';
}

async function drainOnce(): Promise<boolean> {
  const records = await getPendingUploads();
  // A record left 'uploading' means a previous drain (this tab or another)
  // died mid-chunk. Safe to resend unconditionally - the upload_key unique
  // constraint on the backend makes a duplicate send a no-op, not a
  // duplicate item, so no cross-drain coordination is needed here.
  //
  // A retried 'pending' record (attempts > 0) is gated by a linear backoff
  // on updatedAt so a persistent failure doesn't burn through MAX_ATTEMPTS
  // in a single tight loop within one startDrain() call - each attempt
  // needs its own drain pass, not just its own loop iteration.
  const now = Date.now();
  const actionable = records.filter((r) => {
    if (r.status === 'uploading') return true;
    if (r.status !== 'pending') return false;
    if (r.attempts === 0) return true;
    return now - r.updatedAt >= r.attempts * RETRY_BACKOFF_BASE_MS;
  });
  if (actionable.length === 0) return false;

  // A chunk request carries one skip_ai value - keep chunks homogeneous
  // rather than threading a per-file flag through the endpoint.
  const skipAi = actionable[0].skipAi;
  const matching = actionable.filter((r) => r.skipAi === skipAi);
  const chunk: QueuedUpload[] = [];
  let chunkBytes = 0;
  for (const record of matching) {
    if (chunk.length >= effectiveChunkSize) break;
    // Always take at least one file, even if it alone exceeds the budget -
    // a single oversized file must still make progress, not stall forever.
    if (chunk.length > 0 && chunkBytes + record.size > BULK_UPLOAD_MAX_BYTES) break;
    chunk.push(record);
    chunkBytes += record.size;
  }

  for (const record of chunk) {
    await markUploading(record.id);
  }
  await emit();

  try {
    const response = await uploadChunkWithinServerLimit(chunk);
    await Promise.all(
      response.results.map(async (result, idx) => {
        const record = chunk[idx];
        if (!record) return;
        if (result.success || result.duplicate) {
          await markDone(record.id);
        } else {
          await markTerminal(record.id, result.error ?? 'Upload failed');
        }
      })
    );
  } catch (error) {
    const message = errorMessage(error);
    await Promise.all(
      chunk.map((record) =>
        record.attempts + 1 >= MAX_ATTEMPTS
          ? markTerminal(record.id, message)
          : markRetryable(record.id, message)
      )
    );
  }

  queryClient?.invalidateQueries({ queryKey: ['items'] });
  await emit();
  return true;
}

let rescheduleTimer: ReturnType<typeof setTimeout> | null = null;

function clearReschedule(): void {
  if (rescheduleTimer !== null) {
    clearTimeout(rescheduleTimer);
    rescheduleTimer = null;
  }
}

// When every pending record is inside its retry backoff window, drainOnce()
// has nothing actionable and returns false, so the loop below exits and
// isDraining flips back to false - correctly, so the UI doesn't show a
// spinner for the whole backoff wait. But without this, nothing ever calls
// startDrain() again except a page reload or new items being added, so a
// batch that all landed in backoff at once (e.g. every record in a chunk hit
// the same network failure) wedges permanently. This finds the soonest a
// record becomes actionable and arms a timer to resume then.
async function nextBackoffDelayMs(): Promise<number | null> {
  const records = await getPendingUploads();
  const now = Date.now();
  let minDelay: number | null = null;
  for (const record of records) {
    if (record.status !== 'pending' || record.attempts === 0) continue;
    const readyAt = record.updatedAt + record.attempts * RETRY_BACKOFF_BASE_MS;
    const delay = readyAt - now;
    if (delay > 0 && (minDelay === null || delay < minDelay)) {
      minDelay = delay;
    }
  }
  return minDelay;
}

export async function startDrain(): Promise<void> {
  if (isDraining) return;
  clearReschedule();
  isDraining = true;
  await emit();
  try {
    await purgeAbandoned();
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const madeProgress = await drainOnce();
      if (!madeProgress) break;
    }
  } finally {
    isDraining = false;
    await emit();
  }

  const delay = await nextBackoffDelayMs();
  if (delay !== null) {
    rescheduleTimer = setTimeout(() => {
      rescheduleTimer = null;
      void startDrain();
    }, delay);
  }
}

export async function retry(id: string): Promise<void> {
  await markPendingForRetry(id);
  void startDrain();
}

export async function retryAll(): Promise<void> {
  const { terminalRecords } = await computeState();
  await Promise.all(terminalRecords.map((r) => markPendingForRetry(r.id)));
  void startDrain();
}

export async function dismiss(id: string): Promise<void> {
  await dismissRecord(id);
  await emit();
}

export async function dismissAll(): Promise<void> {
  const { terminalRecords } = await computeState();
  await Promise.all(terminalRecords.map((r) => dismissRecord(r.id)));
  await emit();
}

export async function cancelAll(): Promise<void> {
  // Unlike dismissAll (terminal records only), this also clears records
  // stuck in 'pending'/'uploading' - the only recovery path for a record
  // whose durable write to IndexedDB never actually landed, so it never
  // becomes terminal on its own.
  clearReschedule();
  const records = await getPendingUploads();
  await Promise.all(records.map((r) => dismissRecord(r.id)));
  await emit();
}
