// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.
// Do not edit by hand; run `corepack pnpm run vocab:gen`.
export const CLOTHING_TYPE_VALUES = ['shirt', 't-shirt', 'top', 'pants', 'jeans', 'shorts', 'dress', 'jumpsuit', 'skirt', 'jacket', 'coat', 'sweater', 'hoodie', 'blazer', 'suit', 'vest', 'cardigan', 'polo', 'blouse', 'tank-top', 'shoes', 'sneakers', 'boots', 'sandals', 'socks', 'tie', 'hat', 'scarf', 'belt', 'bag', 'accessories'] as const;
export const MATERIAL_VALUES = ['cotton', 'denim', 'leather', 'wool', 'polyester', 'silk', 'linen', 'knit', 'fleece', 'suede', 'velvet', 'nylon', 'canvas', 'down', 'shearling'] as const;
export const FORMALITY_VALUES = ['very-casual', 'casual', 'smart-casual', 'business-casual', 'formal', 'very-formal'] as const;

export const ITEM_ROLE: Record<string, string> = {
  shirt: 'base_top',
  't-shirt': 'base_top',
  top: 'base_top',
  pants: 'bottom',
  jeans: 'bottom',
  shorts: 'bottom',
  dress: 'full_body',
  jumpsuit: 'full_body',
  skirt: 'bottom',
  jacket: 'outer_layer',
  coat: 'outer_layer',
  sweater: 'base_top',
  hoodie: 'outer_layer',
  blazer: 'outer_layer',
  suit: 'suit',
  vest: 'mid_layer',
  cardigan: 'mid_layer',
  polo: 'base_top',
  blouse: 'base_top',
  'tank-top': 'base_top',
  shoes: 'footwear',
  sneakers: 'footwear',
  boots: 'footwear',
  sandals: 'footwear',
  socks: 'socks',
  tie: 'neckwear',
  hat: 'accessory',
  scarf: 'accessory',
  belt: 'accessory',
  bag: 'accessory',
  accessories: 'accessory',
};
