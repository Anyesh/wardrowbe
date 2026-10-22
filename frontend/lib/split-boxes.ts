/** A box as fractions (0-1) of a photo's width and height. */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

export type Handle = 'nw' | 'ne' | 'sw' | 'se';

/** Smallest side a box may have, as a share of the photo. Matches what the server accepts. */
export const MIN_BOX_SIDE = 0.05;
export const MAX_BOXES = 8;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/** Keeps a box inside the photo and at least the minimum size. */
export function clampBox(box: Box): Box {
  const width = clamp(box.width, MIN_BOX_SIDE, 1);
  const height = clamp(box.height, MIN_BOX_SIDE, 1);
  return {
    left: clamp(box.left, 0, 1 - width),
    top: clamp(box.top, 0, 1 - height),
    width,
    height,
  };
}

/** Moves a box by a fraction of the photo, stopping at the photo's edges. */
export function moveBox(box: Box, dx: number, dy: number): Box {
  return clampBox({ ...box, left: box.left + dx, top: box.top + dy });
}

/** Drags one corner of a box; the opposite corner stays where it is. */
export function resizeBox(box: Box, handle: Handle, dx: number, dy: number): Box {
  let left = box.left;
  let top = box.top;
  let right = box.left + box.width;
  let bottom = box.top + box.height;

  if (handle === 'nw' || handle === 'sw') left = clamp(left + dx, 0, right - MIN_BOX_SIDE);
  else right = clamp(right + dx, left + MIN_BOX_SIDE, 1);

  if (handle === 'nw' || handle === 'ne') top = clamp(top + dy, 0, bottom - MIN_BOX_SIDE);
  else bottom = clamp(bottom + dy, top + MIN_BOX_SIDE, 1);

  return { left, top, width: right - left, height: bottom - top };
}

/** A starting box for one the user adds by hand: centred, offset a little from earlier ones. */
export function newBox(existing: number): Box {
  const offset = (existing % 5) * 0.04;
  return clampBox({ left: 0.3 + offset, top: 0.3 + offset, width: 0.4, height: 0.4 });
}
