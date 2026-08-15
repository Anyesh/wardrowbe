const DB_NAME = 'wardrobe_upload_queue';
const DB_VERSION = 1;
const STORE_NAME = 'pending_uploads';
const META_STORE_NAME = 'meta';
const ABANDONED_TTL_MS = 90 * 24 * 60 * 60 * 1000;

export type UploadStatus = 'pending' | 'uploading' | 'done' | 'failed';

export interface QueuedUpload {
  id: string;
  file: Blob;
  filename: string;
  size: number;
  lastModified: number;
  skipAi: boolean;
  addedAt: number;
  updatedAt: number;
  status: UploadStatus;
  attempts: number;
  lastError: string | null;
  terminal: boolean;
}

function hasIndexedDb(): boolean {
  return typeof indexedDB !== 'undefined';
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(META_STORE_NAME)) {
        db.createObjectStore(META_STORE_NAME, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function reqToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  storeName: string,
  fn: (store: IDBObjectStore) => IDBRequest<T> | Promise<T>
): Promise<T> {
  const db = await openDb();
  try {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const result = fn(store);
    return result instanceof IDBRequest ? await reqToPromise(result) : await result;
  } finally {
    db.close();
  }
}

async function putRecord(record: QueuedUpload): Promise<void> {
  await withStore('readwrite', STORE_NAME, (store) => store.put(record));
}

async function getRecord(id: string): Promise<QueuedUpload | undefined> {
  return withStore('readonly', STORE_NAME, (store) => store.get(id));
}

async function deleteRecord(id: string): Promise<void> {
  await withStore('readwrite', STORE_NAME, (store) => store.delete(id));
}

async function getAllRecords(): Promise<QueuedUpload[]> {
  return withStore('readonly', STORE_NAME, (store) => store.getAll());
}

async function getMeta(key: string): Promise<unknown> {
  const row = await withStore('readonly', META_STORE_NAME, (store) => store.get(key));
  return (row as { key: string; value: unknown } | undefined)?.value;
}

async function setMeta(key: string, value: unknown): Promise<void> {
  await withStore('readwrite', META_STORE_NAME, (store) => store.put({ key, value }));
}

export async function requestPersistedStorage(): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.storage?.persist) {
    return false;
  }
  try {
    const granted = await navigator.storage.persist();
    if (hasIndexedDb()) {
      await setMeta('storagePersisted', granted);
    }
    return granted;
  } catch {
    return false;
  }
}

export async function getStoragePersisted(): Promise<boolean | null> {
  if (!hasIndexedDb()) return null;
  try {
    const value = await getMeta('storagePersisted');
    return typeof value === 'boolean' ? value : null;
  } catch {
    return null;
  }
}

export async function estimateQuota(): Promise<{ quota: number; usage: number } | null> {
  if (typeof navigator === 'undefined' || !navigator.storage?.estimate) {
    return null;
  }
  try {
    const { quota, usage } = await navigator.storage.estimate();
    if (quota === undefined || usage === undefined) return null;
    return { quota, usage };
  } catch {
    return null;
  }
}

async function findReusableRecord(
  file: File
): Promise<QueuedUpload | undefined> {
  const records = await getAllRecords();
  return records.find(
    (r) =>
      !r.terminal &&
      r.filename === file.name &&
      r.size === file.size &&
      r.lastModified === file.lastModified
  );
}

export async function enqueueFiles(
  files: File[],
  skipAi: boolean
): Promise<{ staged: string[]; unprotected: File[] }> {
  if (!hasIndexedDb()) {
    return { staged: [], unprotected: files };
  }

  if ((await getStoragePersisted()) === null) {
    await requestPersistedStorage();
  }

  const staged: string[] = [];
  const unprotected: File[] = [];

  for (const file of files) {
    try {
      const reusable = await findReusableRecord(file);
      if (reusable) {
        staged.push(reusable.id);
        continue;
      }

      const now = Date.now();
      const id = crypto.randomUUID();
      const record: QueuedUpload = {
        id,
        file,
        filename: file.name,
        size: file.size,
        lastModified: file.lastModified,
        skipAi,
        addedAt: now,
        updatedAt: now,
        status: 'pending',
        attempts: 0,
        lastError: null,
        terminal: false,
      };
      await putRecord(record);
      staged.push(id);
    } catch {
      // QuotaExceededError or any other staging failure - this file can't be
      // made durable, so it falls through to the caller's non-durable path
      // instead of losing it silently.
      unprotected.push(file);
    }
  }

  return { staged, unprotected };
}

export async function getPendingUploads(): Promise<QueuedUpload[]> {
  if (!hasIndexedDb()) return [];
  const records = await getAllRecords();
  return records.filter((r) => r.status !== 'done');
}

export async function markUploading(id: string): Promise<void> {
  const record = await getRecord(id);
  if (!record) return;
  record.status = 'uploading';
  record.updatedAt = Date.now();
  await putRecord(record);
}

export async function markDone(id: string): Promise<void> {
  await deleteRecord(id);
}

export async function markRetryable(id: string, error: string): Promise<void> {
  const record = await getRecord(id);
  if (!record) return;
  record.status = 'pending';
  record.terminal = false;
  record.attempts += 1;
  record.lastError = error;
  record.updatedAt = Date.now();
  await putRecord(record);
}

export async function markPendingForRetry(id: string): Promise<void> {
  const record = await getRecord(id);
  if (!record) return;
  // A user clicking "retry" on one specific failed file is an explicit,
  // deliberate action - it must run on the next drain pass, not wait out
  // the same backoff that throttles automatic network-failure retries, so
  // this resets attempts rather than incrementing it like markRetryable.
  record.status = 'pending';
  record.terminal = false;
  record.attempts = 0;
  record.lastError = null;
  record.updatedAt = Date.now();
  await putRecord(record);
}

export async function markTerminal(id: string, error: string): Promise<void> {
  const record = await getRecord(id);
  if (!record) return;
  record.status = 'failed';
  record.terminal = true;
  record.lastError = error;
  record.updatedAt = Date.now();
  await putRecord(record);
}

export async function dismiss(id: string): Promise<void> {
  await deleteRecord(id);
}

export async function purgeAbandoned(maxAgeMs: number = ABANDONED_TTL_MS): Promise<void> {
  if (!hasIndexedDb()) return;
  const cutoff = Date.now() - maxAgeMs;
  const records = await getAllRecords();
  await Promise.all(
    records.filter((r) => r.updatedAt < cutoff).map((r) => deleteRecord(r.id))
  );
}
