export const API_BASE_PATH = '/api/v1';

interface FetchOptions extends RequestInit {
  params?: Record<string, string>;
}

export type ApiErrorParams = Record<string, string | number>;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function readParams(value: unknown): ApiErrorParams {
  const params: ApiErrorParams = {};
  for (const [key, entry] of Object.entries(asRecord(value) ?? {})) {
    if (typeof entry === 'string' || typeof entry === 'number') params[key] = entry;
  }
  return params;
}

// message is the server's English text, kept for logs; the UI shows describeError's translation.
class ApiError extends Error {
  status: number;
  data: unknown;
  code: string | null;
  params: ApiErrorParams;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
    const body = asRecord(data);
    this.code = typeof body?.error_code === 'string' ? body.error_code : null;
    this.params = readParams(body?.params);
  }
}

export type NetworkErrorKind = 'offline' | 'unreachable';

class NetworkError extends Error {
  kind: NetworkErrorKind;

  constructor(kind: NetworkErrorKind) {
    super(kind === 'offline' ? 'Offline' : 'Server unreachable');
    this.kind = kind;
    this.name = 'NetworkError';
  }
}

export function networkErrorNow(): NetworkError {
  return new NetworkError(navigator.onLine ? 'unreachable' : 'offline');
}

export function apiErrorFromBody(status: number, data: unknown): ApiError {
  const detail = asRecord(data)?.detail;
  const nested = asRecord(detail)?.message;
  const message =
    typeof detail === 'string' ? detail : typeof nested === 'string' ? nested : `HTTP ${status}`;
  return new ApiError(message, status, data);
}

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function fetchApi<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options;

  let url = `${API_BASE_PATH}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: 'include',
    });
  } catch {
    throw networkErrorNow();
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw apiErrorFromBody(response.status, data);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string, options?: FetchOptions) =>
    fetchApi<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, data?: unknown, options?: FetchOptions) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),

  patch: <T>(endpoint: string, data?: unknown, options?: FetchOptions) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    }),

  delete: <T>(endpoint: string, options?: FetchOptions) =>
    fetchApi<T>(endpoint, { ...options, method: 'DELETE' }),
};

export { ApiError, NetworkError };
