import Taro from '@tarojs/taro'
import { CLOUDBASE_ENV_ID, CLOUDBASE_SERVICE } from '../shared/constants'
import { getAccessToken, getApiBaseUrl } from './session'

export interface ApiOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: unknown
  params?: Record<string, string | number | boolean | undefined | null>
}

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, message: string, data: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

function buildQuery(params?: ApiOptions['params']): string {
  if (!params) return ''
  const pairs = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  return pairs.length ? `?${pairs.join('&')}` : ''
}

function getHeaders(): Record<string, string> {
  const token = getAccessToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

function canUseCloudContainer(): boolean {
  const cloud = (Taro as unknown as { cloud?: { callContainer?: Function } }).cloud
  return Taro.getEnv() === Taro.ENV_TYPE.WEAPP && Boolean(CLOUDBASE_ENV_ID && CLOUDBASE_SERVICE && cloud?.callContainer)
}

async function requestViaCloudContainer<T>(path: string, options: ApiOptions): Promise<T> {
  const cloud = (Taro as unknown as {
    cloud?: {
      callContainer?: (options: {
        config: { env: string }
        path: string
        method: string
        header: Record<string, string>
        data?: unknown
        service: string
      }) => Promise<{ statusCode?: number; data?: unknown }>
    }
  }).cloud

  const response = await cloud!.callContainer!({
    config: { env: CLOUDBASE_ENV_ID },
    service: CLOUDBASE_SERVICE,
    path: `/api/v1${path}${buildQuery(options.params)}`,
    method: options.method || 'GET',
    header: getHeaders(),
    data: options.data,
  })

  const statusCode = response.statusCode || 200
  const data = response.data
  if (statusCode < 200 || statusCode >= 300) {
    const payload = data as { detail?: string } | undefined
    throw new ApiError(statusCode, payload?.detail || 'Request failed', data)
  }

  return data as T
}

async function requestViaHttp<T>(path: string, options: ApiOptions): Promise<T> {
  const baseUrl = getApiBaseUrl()
  if (!baseUrl) {
    throw new ApiError(400, 'API base URL is not configured', null)
  }

  const response = await Taro.request({
    url: `${baseUrl}/api/v1${path}${buildQuery(options.params)}`,
    method: options.method || 'GET',
    data: options.data,
    header: getHeaders(),
  })

  if (response.statusCode < 200 || response.statusCode >= 300) {
    const payload = response.data as { detail?: string } | undefined
    throw new ApiError(response.statusCode, payload?.detail || 'Request failed', response.data)
  }

  return response.data as T
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  if (canUseCloudContainer()) {
    return requestViaCloudContainer<T>(path, options)
  }
  return requestViaHttp<T>(path, options)
}
