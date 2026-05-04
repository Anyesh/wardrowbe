import Taro from '@tarojs/taro'
import { DEFAULT_API_BASE_URL } from '../shared/constants'

const TOKEN_KEY = 'wardrowbe_access_token'
const API_BASE_KEY = 'wardrowbe_api_base_url'
const LAST_SUGGESTION_ID_KEY = 'wardrowbe_last_suggestion_id'

export function getAccessToken(): string {
  return Taro.getStorageSync(TOKEN_KEY) || ''
}

export function setAccessToken(token: string): void {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  Taro.removeStorageSync(TOKEN_KEY)
}

export function getApiBaseUrl(): string {
  return (Taro.getStorageSync(API_BASE_KEY) || DEFAULT_API_BASE_URL || '').replace(/\/$/, '')
}

export function setApiBaseUrl(url: string): void {
  Taro.setStorageSync(API_BASE_KEY, url.replace(/\/$/, ''))
}

export function setLastSuggestionId(id: string): void {
  Taro.setStorageSync(LAST_SUGGESTION_ID_KEY, id)
}

export function getLastSuggestionId(): string {
  return Taro.getStorageSync(LAST_SUGGESTION_ID_KEY) || ''
}
