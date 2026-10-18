// An outfit as one portrait image (1080x1350, the size chat apps and stories crop least),
// drawn in the browser from the item photos so nothing leaves the device until it is shared.

const WIDTH = 1080;
const HEIGHT = 1350;
const MARGIN = 48;
const GAP = 24;
const HEADER = 150;
const FOOTER = 70;
// Nine tiles at most; a longer outfit shows eight photos and a "+N" tile for the rest.
const MAX_TILES = 9;

/** Some photos could not be loaded (often an expired link): the picture would be missing
 * pieces, so nothing is exported. */
export class MissingPhotosError extends Error {
  constructor(readonly missing: number) {
    super(`${missing} photo(s) could not be loaded`);
    this.name = 'MissingPhotosError';
  }
}

export interface CollageText {
  title: string;
  subtitle?: string;
  footer: string;
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

function columnsFor(count: number): number {
  if (count <= 1) return 1;
  if (count <= 4) return 2;
  return 3;
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export async function renderOutfitCollage(imageUrls: string[], text: CollageText): Promise<Blob> {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas is not available');

  ctx.fillStyle = '#f6f5f2';
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  ctx.fillStyle = '#111111';
  ctx.font = '600 56px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText(text.title, MARGIN, MARGIN + 52, WIDTH - 2 * MARGIN);
  if (text.subtitle) {
    ctx.fillStyle = '#6b6b6b';
    ctx.font = '400 34px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.fillText(text.subtitle, MARGIN, MARGIN + 100, WIDTH - 2 * MARGIN);
  }

  if (imageUrls.length === 0) throw new MissingPhotosError(0);
  const overflow = imageUrls.length > MAX_TILES ? imageUrls.length - (MAX_TILES - 1) : 0;
  const shown = overflow ? imageUrls.slice(0, MAX_TILES - 1) : imageUrls;
  const loaded = await Promise.all(shown.map(loadImage));
  const missing = loaded.filter((image) => image === null).length;
  if (missing) throw new MissingPhotosError(missing);
  const images = loaded as HTMLImageElement[];
  const tiles = images.length + (overflow ? 1 : 0);
  const columns = columnsFor(tiles);
  const rows = Math.max(1, Math.ceil(tiles / columns));
  const areaTop = MARGIN + HEADER;
  const areaHeight = HEIGHT - areaTop - FOOTER - MARGIN;
  const cellW = (WIDTH - 2 * MARGIN - (columns - 1) * GAP) / columns;
  const cellH = (areaHeight - (rows - 1) * GAP) / rows;

  images.forEach((image, index) => {
    const x = MARGIN + (index % columns) * (cellW + GAP);
    const y = areaTop + Math.floor(index / columns) * (cellH + GAP);
    ctx.save();
    roundedRect(ctx, x, y, cellW, cellH, 28);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
    ctx.clip();
    const scale = Math.min((cellW - 32) / image.width, (cellH - 32) / image.height);
    const w = image.width * scale;
    const h = image.height * scale;
    ctx.drawImage(image, x + (cellW - w) / 2, y + (cellH - h) / 2, w, h);
    ctx.restore();
  });

  if (overflow) {
    const index = images.length;
    const x = MARGIN + (index % columns) * (cellW + GAP);
    const y = areaTop + Math.floor(index / columns) * (cellH + GAP);
    roundedRect(ctx, x, y, cellW, cellH, 28);
    ctx.fillStyle = '#e7e4dd';
    ctx.fill();
    ctx.fillStyle = '#444444';
    ctx.font = '600 72px system-ui, -apple-system, Segoe UI, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`+${overflow}`, x + cellW / 2, y + cellH / 2);
    ctx.textAlign = 'start';
    ctx.textBaseline = 'alphabetic';
  }

  ctx.fillStyle = '#9a9a9a';
  ctx.font = '500 28px system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.fillText(text.footer, MARGIN, HEIGHT - MARGIN, WIDTH - 2 * MARGIN);

  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Export failed'))), 'image/png')
  );
}

/** Opens the system share sheet with the picture, or downloads it where sharing files is not
 * supported. Returns how it was delivered. */
export async function shareOrDownload(
  blob: Blob,
  filename: string,
  title: string
): Promise<'shared' | 'downloaded' | 'cancelled'> {
  const file = new File([blob], filename, { type: 'image/png' });
  if (typeof navigator !== 'undefined' && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title });
      return 'shared';
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled';
    }
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return 'downloaded';
}
