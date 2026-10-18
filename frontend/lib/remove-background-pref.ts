// Whether new photos get their background removed, remembered per browser; on by default so new
// photos come out clean. Shared by the upload dialog and the photo manager.
const REMOVE_BACKGROUND_KEY = 'wardrowbe.removeBackground';

export function readRemoveBackground(): boolean {
  try {
    return window.localStorage.getItem(REMOVE_BACKGROUND_KEY) !== 'false';
  } catch {
    return true;
  }
}

export function storeRemoveBackground(value: boolean): void {
  try {
    window.localStorage.setItem(REMOVE_BACKGROUND_KEY, String(value));
  } catch {
    // Private mode or blocked storage: the choice just isn't remembered.
  }
}
