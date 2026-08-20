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
import type { BulkUploadResponse } from '@/lib/hooks/use-items';

const BULK_UPLOAD_CHUNK_SIZE = 20;
const MAX_ATTEMPTS = 5;
const RETRY_BACKOFF_BASE_MS = 5000;

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
  e.preventDefault();
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
    throw new Error(`Bulk upload request failed with status ${response.status}`);
  }
  return response.json();
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
  const chunk = actionable.filter((r) => r.skipAi === skipAi).slice(0, BULK_UPLOAD_CHUNK_SIZE);

  for (const record of chunk) {
    await markUploading(record.id);
  }
  await emit();

  try {
    const response = await uploadChunk(chunk);
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

export async function startDrain(): Promise<void> {
  if (isDraining) return;
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
  const records = await getPendingUploads();
  await Promise.all(records.map((r) => dismissRecord(r.id)));
  await emit();
}
