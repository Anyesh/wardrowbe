export const API_BASE_PATH = '/api/v1';

interface FetchOptions extends RequestInit {
  params?: Record<string, string>;
}

type ErrorBody = {
  error_code?: unknown;
  error_params?: unknown;
  detail?: { error_code?: unknown } | string;
} | null;

class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }

  // Older endpoints nest the code in detail; newer ones put it beside a plain-string detail.
  get code(): string | undefined {
    const body = this.data as ErrorBody;
    const nested = typeof body?.detail === 'object' ? body.detail?.error_code : undefined;
    const code = body?.error_code ?? nested;
    return typeof code === 'string' ? code : undefined;
  }

  get params(): Record<string, string | number> | undefined {
    const params = (this.data as ErrorBody)?.error_params;
    return params && typeof params === 'object' ? (params as Record<string, string | number>) : undefined;
  }
}

export type NetworkErrorKind = 'offline' | 'unreachable' | 'cancelled';

class NetworkError extends Error {
  kind: NetworkErrorKind;

  constructor(kind: NetworkErrorKind = 'unreachable') {
    super(`Network request failed (${kind})`);
    this.kind = kind;
    this.name = 'NetworkError';
  }
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
  } catch (err) {
    if (!navigator.onLine) {
      throw new NetworkError('offline');
    }
    throw new NetworkError('unreachable');
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = (typeof data.detail === 'string' ? data.detail : data.detail?.message)
      || data.error?.message
      || 'An error occurred';
    throw new ApiError(message, response.status, data);
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
