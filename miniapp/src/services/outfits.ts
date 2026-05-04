import type { Outfit, OutfitListResponse, SuggestRequest } from '../shared/types'
import { apiRequest } from './api'

export interface OutfitFilters {
  page?: number
  pageSize?: number
  status?: string
  occasion?: string
  source?: string
  search?: string
  is_lookbook?: boolean
  is_replacement?: boolean
}

export function getOutfits(filters: OutfitFilters = {}) {
  return apiRequest<OutfitListResponse>('/outfits', {
    params: {
      page: filters.page || 1,
      page_size: filters.pageSize || 20,
      status: filters.status,
      occasion: filters.occasion,
      source: filters.source,
      search: filters.search,
      is_lookbook: filters.is_lookbook,
      is_replacement: filters.is_replacement,
    },
  })
}

export function getOutfit(id: string) {
  return apiRequest<Outfit>(`/outfits/${id}`)
}

export function suggestOutfit(payload: SuggestRequest) {
  return apiRequest<Outfit>('/outfits/suggest', { method: 'POST', data: payload })
}

export function acceptOutfit(id: string) {
  return apiRequest<Outfit>(`/outfits/${id}/accept`, { method: 'POST', data: {} })
}

export function rejectOutfit(id: string) {
  return apiRequest<Outfit>(`/outfits/${id}/reject`, { method: 'POST', data: {} })
}

export function submitFeedback(
  id: string,
  payload: {
    accepted?: boolean
    rating?: number
    comment?: string
    actually_worn?: boolean
    wore_instead_items?: string[]
  }
) {
  return apiRequest(`/outfits/${id}/feedback`, { method: 'POST', data: payload })
}
