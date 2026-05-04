import Taro from '@tarojs/taro'
import type {
  AnalyticsResponse,
  ForecastResponse,
  Preferences,
  UserProfile,
  UserSyncResponse,
  WeatherData,
} from '../shared/types'
import { apiRequest } from './api'
import { setAccessToken } from './session'

export function getWeather(latitude?: number, longitude?: number) {
  return apiRequest<WeatherData>('/weather/current', {
    params: {
      latitude,
      longitude,
    },
  })
}

export function getForecast(latitude?: number, longitude?: number, days = 7) {
  return apiRequest<ForecastResponse>('/weather/forecast', {
    params: {
      latitude,
      longitude,
      days,
    },
  })
}

export function getPreferences() {
  return apiRequest<Preferences>('/users/me/preferences')
}

export function updatePreferences(data: Partial<Preferences>) {
  return apiRequest<Preferences>('/users/me/preferences', { method: 'PATCH', data })
}

export function getUserProfile() {
  return apiRequest<UserProfile>('/users/me')
}

export function updateUserProfile(data: Partial<UserProfile>) {
  return apiRequest<UserProfile>('/users/me', { method: 'PATCH', data })
}

export function getAnalyticsSummary() {
  return apiRequest<AnalyticsResponse>('/analytics')
}

export async function syncWeChatMiniapp(displayName?: string, avatarUrl?: string) {
  let code: string | undefined
  if (Taro.getEnv() === Taro.ENV_TYPE.WEAPP) {
    const login = await Taro.login()
    code = login.code
  }

  const response = await apiRequest<UserSyncResponse>('/auth/wechat-miniapp/sync', {
    method: 'POST',
    data: {
      code,
      display_name: displayName,
      avatar_url: avatarUrl,
    },
  })
  setAccessToken(response.access_token)
  return response
}
