// Extensions must stay within IMAGE_MIME_TYPES in backend/app/services/image_service.py.
export const ACCEPTED_IMAGE_TYPES = {
  'image/*': ['.jpeg', '.jpg', '.png', '.webp', '.heic', '.heif'],
};

// Native <input type="file"> takes a comma-separated list rather than react-dropzone's map.
export const ACCEPTED_IMAGE_INPUT = Object.values(ACCEPTED_IMAGE_TYPES).flat().join(',');
