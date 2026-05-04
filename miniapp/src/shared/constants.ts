export const DEFAULT_API_BASE_URL = process.env.TARO_APP_API_BASE_URL || ''
export const CLOUDBASE_ENV_ID = process.env.TARO_APP_CLOUDBASE_ENV_ID || ''
export const CLOUDBASE_SERVICE = process.env.TARO_APP_CLOUDBASE_SERVICE || ''

export const CLOTHING_COLORS = [
  { name: '黑色', value: 'black', hex: '#1a1a1a' },
  { name: '灰色', value: 'gray', hex: '#808080' },
  { name: '白色', value: 'white', hex: '#fafafa' },
  { name: '米色', value: 'beige', hex: '#d4c4a8' },
  { name: '橄榄色', value: 'olive', hex: '#707b52' },
  { name: '绿色', value: 'green', hex: '#4a7c59' },
  { name: '青绿色', value: 'teal', hex: '#367588' },
  { name: '藏蓝色', value: 'navy', hex: '#1b2a4a' },
  { name: '蓝色', value: 'blue', hex: '#4a7db8' },
  { name: '棕色', value: 'brown', hex: '#8b5a3c' },
  { name: '酒红色', value: 'burgundy', hex: '#722f37' },
  { name: '红色', value: 'red', hex: '#c44536' },
  { name: '粉色', value: 'pink', hex: '#e8a0b0' },
  { name: '紫色', value: 'purple', hex: '#6b5b7a' },
  { name: '黄色', value: 'yellow', hex: '#d4a84b' },
  { name: '橙色', value: 'orange', hex: '#d2691e' },
] as const

export const CLOTHING_TYPES = [
  { label: '衬衫', value: 'shirt' },
  { label: 'T 恤', value: 't-shirt' },
  { label: '毛衣', value: 'sweater' },
  { label: '卫衣', value: 'hoodie' },
  { label: '长裤', value: 'pants' },
  { label: '牛仔裤', value: 'jeans' },
  { label: '短裤', value: 'shorts' },
  { label: '裙子', value: 'skirt' },
  { label: '连衣裙', value: 'dress' },
  { label: '夹克', value: 'jacket' },
  { label: '西装外套', value: 'blazer' },
  { label: '大衣', value: 'coat' },
  { label: '鞋子', value: 'shoes' },
  { label: '配饰', value: 'accessories' },
] as const

export const OCCASIONS = [
  { label: '休闲', value: 'casual' },
  { label: '通勤', value: 'office' },
  { label: '正式', value: 'formal' },
  { label: '约会', value: 'date' },
  { label: '运动', value: 'sporty' },
  { label: '户外', value: 'outdoor' },
] as const

export const OUTFIT_FILTERS = [
  { label: '全部', value: 'all' },
  { label: '我的搭配', value: 'lookbook' },
  { label: '已穿', value: 'accepted' },
  { label: '搭配', value: 'pairing' },
  { label: '替换', value: 'replacement' },
  { label: 'AI', value: 'ai' },
] as const
