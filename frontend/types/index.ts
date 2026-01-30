export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  role: 'admin' | 'member';
  timezone: string;
  location_name?: string;
  onboarding_completed: boolean;
  created_at: string;
}

export interface ClothingItem {
  id: string;
  user_id: string;
  image_path: string;
  image_url: string;
  thumbnail_path?: string;
  thumbnail_url?: string;
  type: string;
  subtype?: string;
  tags: Record<string, unknown>;
  colors: string[];
  primary_color?: string;
  status: 'processing' | 'ready' | 'error' | 'archived';
  wear_count: number;
  last_worn_at?: string;
  name?: string;
  brand?: string;
  favorite: boolean;
  is_archived: boolean;
  created_at: string;
}

export interface Outfit {
  id: string;
  user_id: string;
  weather_data?: WeatherData;
  occasion: string;
  scheduled_for: string;
  reasoning?: string;
  style_notes?: string;
  status: 'pending' | 'sent' | 'viewed' | 'accepted' | 'rejected' | 'expired';
  source: 'scheduled' | 'on_demand' | 'manual';
  items: OutfitItem[];
  created_at: string;
}

export interface OutfitItem {
  item_id: string;
  position: number;
  layer_type?: string;
  item?: ClothingItem;
}

export interface WeatherData {
  temperature: number;
  feels_like: number;
  condition: string;
  humidity: number;
  wind_speed: number;
  precipitation_chance: number;
}

export interface UserPreferences {
  color_favorites: string[];
  color_avoid: string[];
  style_profile: Record<string, number>;
  default_occasion: string;
  temperature_sensitivity: 'cold' | 'normal' | 'warm';
  cold_threshold: number;
  hot_threshold: number;
  avoid_repeat_days: number;
  variety_level: 'low' | 'moderate' | 'high';
}

export interface Family {
  id: string;
  name: string;
  invite_code: string;
  created_at: string;
}
