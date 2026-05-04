export const DEFAULT_API_BASE_URL = process.env.TARO_APP_API_BASE_URL || ''
export const CLOUDBASE_ENV_ID = process.env.TARO_APP_CLOUDBASE_ENV_ID || ''
export const CLOUDBASE_SERVICE = process.env.TARO_APP_CLOUDBASE_SERVICE || ''

export const CLOTHING_COLORS = [
  { name: 'Black', value: 'black', hex: '#1a1a1a' },
  { name: 'Gray', value: 'gray', hex: '#808080' },
  { name: 'White', value: 'white', hex: '#fafafa' },
  { name: 'Beige', value: 'beige', hex: '#d4c4a8' },
  { name: 'Olive', value: 'olive', hex: '#707b52' },
  { name: 'Green', value: 'green', hex: '#4a7c59' },
  { name: 'Teal', value: 'teal', hex: '#367588' },
  { name: 'Navy', value: 'navy', hex: '#1b2a4a' },
  { name: 'Blue', value: 'blue', hex: '#4a7db8' },
  { name: 'Brown', value: 'brown', hex: '#8b5a3c' },
  { name: 'Burgundy', value: 'burgundy', hex: '#722f37' },
  { name: 'Red', value: 'red', hex: '#c44536' },
  { name: 'Pink', value: 'pink', hex: '#e8a0b0' },
  { name: 'Purple', value: 'purple', hex: '#6b5b7a' },
  { name: 'Yellow', value: 'yellow', hex: '#d4a84b' },
  { name: 'Orange', value: 'orange', hex: '#d2691e' },
] as const

export const CLOTHING_TYPES = [
  { label: 'Shirt', value: 'shirt' },
  { label: 'T-Shirt', value: 't-shirt' },
  { label: 'Sweater', value: 'sweater' },
  { label: 'Hoodie', value: 'hoodie' },
  { label: 'Pants', value: 'pants' },
  { label: 'Jeans', value: 'jeans' },
  { label: 'Shorts', value: 'shorts' },
  { label: 'Skirt', value: 'skirt' },
  { label: 'Dress', value: 'dress' },
  { label: 'Jacket', value: 'jacket' },
  { label: 'Blazer', value: 'blazer' },
  { label: 'Coat', value: 'coat' },
  { label: 'Shoes', value: 'shoes' },
  { label: 'Accessories', value: 'accessories' },
] as const

export const OCCASIONS = [
  { label: 'Casual', value: 'casual' },
  { label: 'Office', value: 'office' },
  { label: 'Formal', value: 'formal' },
  { label: 'Date', value: 'date' },
  { label: 'Sporty', value: 'sporty' },
  { label: 'Outdoor', value: 'outdoor' },
] as const

export const OUTFIT_FILTERS = [
  { label: 'All', value: 'all' },
  { label: 'My Looks', value: 'lookbook' },
  { label: 'Worn', value: 'accepted' },
  { label: 'Pairings', value: 'pairing' },
  { label: 'Replacements', value: 'replacement' },
  { label: 'AI', value: 'ai' },
] as const
