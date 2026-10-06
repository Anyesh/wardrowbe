import { CLOTHING_TYPE_VALUES, OCCASION_VALUES } from '@/lib/generated/garment-vocabulary';

// API response types matching backend schemas

export interface ItemTags {
  colors: string[];
  primary_color?: string;
  pattern?: string;
  material?: string;
  style: string[];
  season: string[];
  formality?: string;
  fit?: string;
  occasion?: string[];
  brand?: string;
  condition?: string;
  features?: string[];
  logprobs_confidence?: number;
}

export interface Item {
  id: string;
  user_id: string;
  type: string;
  subtype?: string | null;
  name?: string;
  brand?: string;
  notes?: string;
  purchase_date?: string;
  purchase_price?: number;
  favorite: boolean;
  image_path: string;
  thumbnail_path?: string;
  medium_path?: string;
  original_image_path?: string | null;
  image_url?: string;
  thumbnail_url?: string;
  medium_url?: string;
  tags: ItemTags;
  colors: string[];
  primary_color?: string;
  status: 'processing' | 'ready' | 'error' | 'archived';
  ai_processed: boolean;
  ai_confidence?: number;
  ai_description?: string;
  ai_error?: string | null;
  ai_unrecognized_type?: string | null;
  ai_started_at?: string | null;
  processing_kind?: 'background_removal' | 'rotate' | null;
  tagging_status: 'pending' | 'tagged';
  tagged_by?: 'auto' | 'manual' | null;
  tagged_at?: string | null;
  wear_count: number;
  last_worn_at?: string;
  last_suggested_at?: string;
  suggestion_count: number;
  acceptance_count: number;
  wears_since_wash: number;
  last_washed_at?: string;
  wash_interval?: number;
  needs_wash: boolean;
  effective_wash_interval: number;
  additional_images: ItemImage[];
  is_archived: boolean;
  archived_at?: string;
  archive_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface ItemListResponse {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface AnalysisInProgress {
  item_id: string;
  name?: string | null;
  type: string;
  image_url?: string | null;
  started_at: string;
}

export interface AnalysisCompletion {
  item_id: string;
  name?: string | null;
  type: string;
  duration_seconds?: number | null;
  completed_at: string;
}

export interface AnalysisFailure {
  item_id: string;
  name?: string | null;
  type: string;
  error?: string | null;
  failed_at?: string | null;
}

export interface TaggingProgress {
  processing: number;
  queued: number;
  analyzing: number;
  failed: number;
  completed: number;
  total: number;
  // Scoped to the run in flight rather than the wardrobe, so an import into a
  // populated wardrobe does not open at 70% and creep.
  batch_total: number;
  batch_completed: number;
  batch_failed: number;
  current: AnalysisInProgress[];
  recent: AnalysisCompletion[];
  failures: AnalysisFailure[];
  avg_duration_seconds?: number | null;
  eta_seconds?: number | null;
  concurrency: number;
}

export interface ItemFilter {
  type?: string;
  subtype?: string;
  colors?: string[];
  status?: string;
  favorite?: boolean;
  needs_wash?: boolean;
  is_archived?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  ids?: string;
}

export interface StyleProfile {
  casual: number;
  formal: number;
  sporty: number;
  minimalist: number;
  bold: number;
}

export interface AIEndpoint {
  name: string;
  url: string;
  vision_model: string;
  text_model: string;
  enabled: boolean;
}

export interface Preferences {
  color_favorites: string[];
  color_avoid: string[];
  style_profile: StyleProfile;
  default_occasion: string;
  temperature_unit: 'celsius' | 'fahrenheit';
  temperature_sensitivity: 'low' | 'normal' | 'high';
  cold_threshold: number;
  hot_threshold: number;
  layering_preference: 'minimal' | 'moderate' | 'heavy';
  avoid_repeat_days: number;
  prefer_underused_items: boolean;
  variety_level: 'low' | 'moderate' | 'high';
  ai_endpoints: AIEndpoint[];
}

export { CLOTHING_COLORS } from '@/lib/generated/garment-vocabulary';

// Picker order is alphabetical by value. The values come from the generated vocabulary, so the
// labels are not stored here: they are translated from constants.types at render time.
export const CLOTHING_TYPES = [...CLOTHING_TYPE_VALUES].sort().map((value) => ({ value }));

export type ClothingTypeValue = (typeof CLOTHING_TYPE_VALUES)[number];

// Suggested subtypes per type. Mirrors the SUBTYPE examples in clothing_analysis.txt.
// Subtype is free text on the backend (and the model may answer outside this list),
// so these are suggestions, not a closed set.
export const CLOTHING_SUBTYPES: Record<string, readonly string[]> = {
  shirt: ['henley', 'button-down', 'oxford', 'flannel', 'hawaiian', 'camp-collar'],
  pants: ['chinos', 'joggers', 'cargo', 'trousers', 'leggings', 'sweatpants'],
  dress: ['sundress', 'slip-dress', 'maxi', 'midi', 'wrap', 'shirt-dress', 'a-line'],
  jacket: ['denim-jacket', 'bomber', 'parka', 'windbreaker', 'trucker', 'anorak'],
  shoes: ['loafers', 'oxfords', 'mules', 'flats', 'heels', 'platforms'],
  sneakers: ['low-top', 'high-top', 'chunky', 'slip-on'],
  boots: ['ankle', 'chelsea', 'combat', 'knee-high', 'rain'],
  skirt: ['mini', 'midi', 'maxi', 'pleated', 'wrap', 'pencil'],
  sweater: ['pullover', 'crewneck', 'turtleneck', 'v-neck'],
  socks: ['ankle', 'crew', 'knee-high', 'no-show', 'dress', 'athletic'],
  tie: ['necktie', 'bow-tie', 'bolo'],
};

export type Occasion = (typeof OCCASION_VALUES)[number];

// Pickers offer only these so that the chip row stays short; the backend accepts every value in
// OCCASION_VALUES, and outfits created through the API can carry any of them.
const FEATURED_OCCASION_VALUES = ['casual', 'office', 'formal', 'date', 'sporty', 'outdoor'] as const satisfies readonly Occasion[];

export type FeaturedOccasion = (typeof FEATURED_OCCASION_VALUES)[number];

export const FEATURED_OCCASIONS = FEATURED_OCCASION_VALUES.map((value) => ({ value }));

// Family types
export interface FamilyMember {
  id: string;
  display_name: string;
  email: string;
  avatar_url?: string;
  role: 'admin' | 'member';
  created_at: string;  // When user joined the family
}

export interface PendingInvite {
  id: string;
  email: string;
  created_at: string;  // When invite was sent
  expires_at: string;
}

export interface Family {
  id: string;
  name: string;
  invite_code: string;
  members: FamilyMember[];
  pending_invites: PendingInvite[];
  created_at: string;
}

export interface FamilyCreateResponse {
  id: string;
  name: string;
  invite_code: string;
  role: string;
}

export interface JoinFamilyResponse {
  family_id: string;
  family_name: string;
  role: string;
}

// Multi-image types
export interface ItemImage {
  id: string;
  item_id: string;
  image_path: string;
  thumbnail_path?: string;
  medium_path?: string;
  position: number;
  created_at: string;
  image_url: string;
  thumbnail_url?: string;
  medium_url?: string;
}

// Wash tracking types
export interface WashHistoryEntry {
  id: string;
  item_id: string;
  washed_at: string;
  method?: string;
  notes?: string;
  created_at: string;
}

export interface FamilyRating {
  id: string;
  user_id: string;
  user_display_name: string;
  user_avatar_url: string | null;
  rating: number;
  comment: string | null;
  created_at: string;
}

export interface OutfitItem {
  id: string;
  type: string;
  subtype: string | null;
  name: string | null;
  primary_color: string | null;
  colors: string[];
  image_path: string | null;
  thumbnail_path: string | null;
  image_url: string | null;
  thumbnail_url: string | null;
  layer_type: string | null;
  position: number;
}

export interface WeatherData {
  temperature: number;
  feels_like: number;
  humidity: number;
  precipitation_chance: number;
  precipitation_mm: number;
  wind_speed: number;
  condition: string;
  condition_code: number;
  is_day: boolean;
  uv_index: number;
  timestamp: string;
  // Optional because outfits stored before the forecast range existed lack these keys.
  temp_min?: number | null;
  temp_max?: number | null;
  window_min?: number | null;
  window_max?: number | null;
}

// /weather/current serves the same snapshot outfits store, minus the wearing-window range.
export type CurrentWeather = Omit<WeatherData, 'window_min' | 'window_max'>;

export interface WoreInsteadItem {
  id: string;
  type: string;
  name: string | null;
  thumbnail_path: string | null;
  thumbnail_url: string | null;
}

export interface FeedbackSummary {
  rating: number | null;
  comment: string | null;
  worn_at: string | null;
  actually_worn: boolean | null;
  wore_instead_items: WoreInsteadItem[] | null;
}

export const OUTFIT_STATUSES = [
  'pending',
  'sent',
  'viewed',
  'accepted',
  'rejected',
  'skipped',
  'expired',
] as const;

export type OutfitStatus = (typeof OUTFIT_STATUSES)[number];

export type OutfitSource = 'scheduled' | 'on_demand' | 'manual' | 'pairing' | 'external';

export interface Outfit {
  id: string;
  occasion: string;
  scheduled_for: string | null;
  status: OutfitStatus;
  name: string | null;
  replaces_outfit_id: string | null;
  cloned_from_outfit_id: string | null;
  source: OutfitSource;
  reasoning: string | null;
  style_notes: string | null;
  season: string | null;
  formality: string | null;
  palette: string[] | null;
  notes: string | null;
  highlights: string[] | null;
  weather: WeatherData | null;
  items: OutfitItem[];
  feedback: FeedbackSummary | null;
  family_ratings: FamilyRating[] | null;
  family_rating_average: number | null;
  family_rating_count: number | null;
  is_starter_suggestion: boolean;
  created_at: string;
}

export interface SuggestRequest {
  occasion: string;
  weather_override?: {
    temperature: number;
    feels_like?: number;
    humidity: number;
    precipitation_chance: number;
    condition: string;
  };
  exclude_items?: string[];
  include_items?: string[];
}

// Pairing types
export interface SourceItem {
  id: string;
  type: string;
  subtype: string | null;
  name: string | null;
  primary_color: string | null;
  image_path: string;
  thumbnail_path: string | null;
  image_url: string;
  thumbnail_url: string | null;
}

export interface PairingItem extends OutfitItem {
  image_path: string;
  image_url: string;
}

export interface Pairing
  extends Pick<
    Outfit,
    | 'id'
    | 'occasion'
    | 'status'
    | 'source'
    | 'reasoning'
    | 'style_notes'
    | 'season'
    | 'formality'
    | 'palette'
    | 'notes'
    | 'highlights'
    | 'family_ratings'
    | 'family_rating_average'
    | 'family_rating_count'
    | 'created_at'
  > {
  scheduled_for: string;
  source_item: SourceItem | null;
  items: PairingItem[];
  feedback: Pick<FeedbackSummary, 'rating' | 'comment' | 'worn_at'> | null;
}

export interface PairingListResponse {
  pairings: Pairing[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface GeneratePairingsRequest {
  num_pairings: number;
}

export interface GeneratePairingsResponse {
  generated: number;
  pairings: Pairing[];
}
