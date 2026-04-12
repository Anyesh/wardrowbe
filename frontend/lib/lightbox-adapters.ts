export type LightboxImage = {
  uri: string;
  placeholderUri?: string;
  itemId?: string;
  itemName?: string;
  itemCategory?: string;
};

export type AdapterResult = {
  images: LightboxImage[];
  indexOf: (id: string) => number;
};

type ImageLike = {
  image_url?: string | null;
  medium_url?: string | null;
  thumbnail_url?: string | null;
};

type ItemLike = ImageLike & {
  id: string;
  name?: string;
  type?: string;
  subtype?: string;
  category?: string;
  primary_color?: string;
  layer_type?: string;
  additional_images?: ImageLike[];
};

type OutfitLike = { id: string; items?: ItemLike[] };

type PairingLike = {
  source_item: ItemLike;
  paired_items?: ItemLike[];
};

function pickUri(img: ImageLike | null | undefined): string | null {
  if (!img) return null;
  return img.image_url || img.medium_url || img.thumbnail_url || null;
}

function pickPlaceholder(img: ImageLike | null | undefined): string | undefined {
  if (!img) return undefined;
  return img.medium_url || img.thumbnail_url || undefined;
}

function itemCategory(item: ItemLike): string | undefined {
  return item.category || [item.type, item.primary_color].filter(Boolean).join(' · ') || undefined;
}

export function itemToLightboxImages(item: ItemLike): AdapterResult {
  const images: LightboxImage[] = [];
  const primary = pickUri(item);
  if (primary) {
    images.push({
      uri: primary,
      placeholderUri: pickPlaceholder(item),
      itemId: item.id,
      itemName: item.name,
      itemCategory: itemCategory(item),
    });
  }
  for (const extra of item.additional_images ?? []) {
    const uri = pickUri(extra);
    if (!uri) continue;
    images.push({
      uri,
      placeholderUri: pickPlaceholder(extra),
      itemId: item.id,
      itemName: item.name,
      itemCategory: itemCategory(item),
    });
  }
  return {
    images,
    indexOf: (id: string) => (images.length > 0 && id === item.id ? 0 : -1),
  };
}

export function outfitToLightboxImages(outfit: OutfitLike): AdapterResult {
  const images: LightboxImage[] = [];
  const idToIndex = new Map<string, number>();
  for (const item of outfit.items ?? []) {
    const uri = pickUri(item);
    if (!uri) continue;
    idToIndex.set(item.id, images.length);
    images.push({
      uri,
      placeholderUri: pickPlaceholder(item),
      itemId: item.id,
      itemName: item.name,
      itemCategory: itemCategory(item),
    });
  }
  return { images, indexOf: (id: string) => idToIndex.get(id) ?? -1 };
}

export function localUrisToLightboxImages(uris: string[]): AdapterResult {
  const images: LightboxImage[] = uris.map((uri) => ({ uri }));
  return { images, indexOf: () => -1 };
}

export function pairingToLightboxImages(pairing: PairingLike): AdapterResult {
  const items: ItemLike[] = [pairing.source_item, ...(pairing.paired_items ?? [])];
  const fauxOutfit: OutfitLike = { id: 'pairing', items };
  return outfitToLightboxImages(fauxOutfit);
}
