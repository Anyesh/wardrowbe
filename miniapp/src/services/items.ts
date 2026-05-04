import Taro from '@tarojs/taro'
import type { Item, ItemFilter, ItemListResponse } from '../shared/types'
import { apiRequest, ApiError } from './api'
import { getAccessToken, getApiBaseUrl } from './session'

export function getItems(filters: ItemFilter = {}, page = 1, pageSize = 20) {
  return apiRequest<ItemListResponse>('/items', {
    params: {
      page,
      page_size: pageSize,
      type: filters.type,
      search: filters.search,
      favorite: filters.favorite,
      needs_wash: filters.needs_wash,
      is_archived: filters.is_archived,
      sort_by: filters.sort_by,
      sort_order: filters.sort_order,
      status: filters.status,
    },
  })
}

export function getItem(id: string) {
  return apiRequest<Item>(`/items/${id}`)
}

export function updateItem(id: string, data: Partial<Item>) {
  return apiRequest<Item>(`/items/${id}`, { method: 'PATCH', data })
}

export function deleteItem(id: string) {
  return apiRequest<void>(`/items/${id}`, { method: 'DELETE' })
}

export function logWash(id: string) {
  return apiRequest<Item>(`/items/${id}/wash`, { method: 'POST', data: {} })
}

export function logWear(id: string, occasion?: string) {
  return apiRequest<Item>(`/items/${id}/wear`, {
    method: 'POST',
    data: occasion ? { occasion } : {},
  })
}

export function reanalyzeItem(id: string) {
  return apiRequest<{ status: string; job_id?: string }>(`/items/${id}/analyze`, { method: 'POST', data: {} })
}

export async function uploadItem(filePath: string, formData: Record<string, string>) {
  const baseUrl = getApiBaseUrl()
  if (!baseUrl) {
    throw new ApiError(400, 'API base URL is required for uploads', null)
  }

  const response = await Taro.uploadFile({
    url: `${baseUrl}/api/v1/items`,
    filePath,
    name: 'image',
    formData,
    header: getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {},
  })

  if (response.statusCode < 200 || response.statusCode >= 300) {
    let detail = 'Upload failed'
    try {
      const data = JSON.parse(response.data) as { detail?: string }
      detail = data.detail || detail
    } catch {
      // ignore parse failure
    }
    throw new ApiError(response.statusCode, detail, response.data)
  }

  return JSON.parse(response.data) as Item
}
