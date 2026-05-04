export type TempUnit = 'celsius' | 'fahrenheit'

export interface ItemTags {
  colors: string[]
  primary_color?: string
  pattern?: string
  material?: string
  style: string[]
  season: string[]
  formality?: string
  fit?: string
  occasion?: string[]
  brand?: string
  condition?: string
  features?: string[]
  logprobs_confidence?: number
}

export interface ItemImage {
  id: string
  item_id: string
  image_path: string
  thumbnail_path?: string
  medium_path?: string
  position: number
  created_at: string
  image_url?: string
  thumbnail_url?: string
  medium_url?: string
}

export interface Item {
  id: string
  user_id: string
  type: string
  subtype?: string
  name?: string
  brand?: string
  notes?: string
  purchase_date?: string
  purchase_price?: number
  favorite: boolean
  image_path: string
  thumbnail_path?: string
  medium_path?: string
  image_url?: string
  thumbnail_url?: string
  medium_url?: string
  tags: ItemTags
  colors: string[]
  primary_color?: string
  pattern?: string
  material?: string
  style?: string[]
  formality?: string
  season?: string[]
  status: 'processing' | 'ready' | 'error' | 'archived'
  ai_processed: boolean
  ai_confidence?: number
  ai_description?: string
  wear_count: number
  last_worn_at?: string
  last_suggested_at?: string
  suggestion_count: number
  acceptance_count: number
  wears_since_wash: number
  last_washed_at?: string
  wash_interval?: number
  needs_wash: boolean
  effective_wash_interval?: number
  additional_images: ItemImage[]
  is_archived: boolean
  archived_at?: string
  archive_reason?: string
  created_at: string
  updated_at: string
}

export interface ItemListResponse {
  items: Item[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface ItemFilter {
  type?: string
  subtype?: string
  colors?: string[]
  status?: string
  favorite?: boolean
  needs_wash?: boolean
  is_archived?: boolean
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface StyleProfile {
  casual: number
  formal: number
  sporty: number
  minimalist: number
  bold: number
}

export interface AIEndpoint {
  name: string
  url: string
  vision_model: string
  text_model: string
  enabled: boolean
}

export interface Preferences {
  color_favorites: string[]
  color_avoid: string[]
  style_profile: StyleProfile
  default_occasion: string
  temperature_unit: TempUnit
  temperature_sensitivity: 'low' | 'normal' | 'high'
  cold_threshold: number
  hot_threshold: number
  layering_preference: 'minimal' | 'moderate' | 'heavy'
  avoid_repeat_days: number
  prefer_underused_items: boolean
  variety_level: 'low' | 'moderate' | 'high'
  ai_endpoints: AIEndpoint[]
}

export interface UserProfile {
  id: string
  email: string
  display_name: string
  avatar_url?: string | null
  timezone: string
  location_lat?: number | null
  location_lon?: number | null
  location_name?: string | null
  family_id?: string | null
  role: string
  onboarding_completed: boolean
  body_measurements?: Record<string, unknown> | null
}

export interface UserSyncResponse {
  id: string
  email: string
  display_name: string
  is_new_user: boolean
  onboarding_completed: boolean
  access_token: string
}

export interface WeatherData {
  temperature: number
  feels_like: number
  humidity: number
  precipitation_chance: number
  precipitation_mm?: number
  wind_speed?: number
  condition: string
  condition_code?: number
  is_day?: boolean
  uv_index?: number
  timestamp?: string
}

export interface ForecastDay {
  date: string
  temp_min: number
  temp_max: number
  precipitation_chance: number
  condition: string
  condition_code: number
}

export interface ForecastResponse {
  latitude: number
  longitude: number
  forecast: ForecastDay[]
}

export interface OutfitItem {
  id: string
  type: string
  subtype?: string
  name?: string
  primary_color?: string
  colors: string[]
  image_path?: string | null
  thumbnail_path?: string | null
  image_url?: string | null
  thumbnail_url?: string | null
  layer_type?: string | null
  position: number
}

export interface FamilyRating {
  id: string
  user_id: string
  user_display_name: string
  user_avatar_url?: string | null
  rating: number
  comment?: string | null
  created_at: string
}

export interface FeedbackSummary {
  rating?: number | null
  comment?: string | null
  worn_at?: string | null
  actually_worn?: boolean | null
}

export type OutfitSource = 'scheduled' | 'on_demand' | 'manual' | 'pairing'
export type OutfitStatus = 'pending' | 'sent' | 'viewed' | 'accepted' | 'rejected' | 'skipped' | 'expired'

export interface Outfit {
  id: string
  occasion: string
  scheduled_for?: string | null
  status: OutfitStatus
  name?: string | null
  source: OutfitSource | string
  reasoning?: string | null
  style_notes?: string | null
  highlights?: string[] | null
  weather?: WeatherData | null
  items: OutfitItem[]
  feedback?: FeedbackSummary | null
  family_ratings?: FamilyRating[] | null
  family_rating_average?: number | null
  family_rating_count?: number | null
  is_starter_suggestion?: boolean
  created_at: string
}

export interface OutfitListResponse {
  outfits: Outfit[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface SuggestRequest {
  occasion?: string
  time_of_day?: 'morning' | 'afternoon' | 'evening' | 'night' | 'full day'
  weather_override?: {
    temperature: number
    feels_like?: number
    humidity: number
    precipitation_chance: number
    condition: string
  }
  exclude_items?: string[]
  include_items?: string[]
}

export interface WardrobeStats {
  total_items: number
  items_by_status: Record<string, number>
  total_outfits: number
  outfits_this_week: number
  outfits_this_month: number
  acceptance_rate?: number | null
  average_rating?: number | null
  total_wears: number
}

export interface AnalyticsResponse {
  wardrobe: WardrobeStats
  color_distribution: Array<{ color: string; count: number; percentage: number }>
  type_distribution: Array<{ type: string; count: number; percentage: number }>
  most_worn: Item[]
  least_worn: Item[]
  never_worn: Item[]
  acceptance_trend: Array<{ period: string; total: number; accepted: number; rejected: number; rate: number }>
  insights: string[]
}
