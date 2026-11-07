import { api } from '@/lib/api';

export interface BulkBatchResponse {
  errors: string[];
  next_cursor?: string | null;
  has_more?: boolean;
}

// The server caps how many rows one bulk request touches. An explicit id list
// is ours to keep under the cap, but a select_all is only filters here, so the
// server walks it and hands back a cursor for the next batch.
const MAX_BULK_BATCHES = 200;

export function mergeBulkBatches<T extends BulkBatchResponse>(
  acc: T,
  batch: T,
  sumKeys: (keyof T)[]
): T {
  const merged = { ...acc, ...batch } as T;
  for (const key of sumKeys) {
    merged[key] = ((acc[key] as number) + (batch[key] as number)) as T[keyof T];
  }
  merged.errors = [...acc.errors, ...batch.errors];
  return merged;
}

export async function drainCursor<T extends BulkBatchResponse>(
  path: string,
  params: object,
  sumKeys: (keyof T)[]
): Promise<T> {
  let batch = await api.post<T>(path, params);
  let merged = batch;

  for (let i = 0; batch.has_more && batch.next_cursor && i < MAX_BULK_BATCHES; i++) {
    batch = await api.post<T>(path, { ...params, after_id: batch.next_cursor });
    merged = mergeBulkBatches(merged, batch, sumKeys);
  }

  return merged;
}
