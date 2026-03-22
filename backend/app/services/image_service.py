import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import imagehash
from PIL import Image

from app.config import get_settings

settings = get_settings()

# Image size configurations
# Thumbnail: Used in cards/grids. 400px supports ~200px display on retina
# Medium: Used in detail views and outfit displays
# Original: Full resolution for zoom/download
SIZES = {
    "thumbnail": (400, 400),
    "medium": (800, 800),
    "original": (2400, 2400),
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class ImageService:
    def __init__(self, storage_path: str | None = None):
        self.storage_path = Path(storage_path or settings.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _get_user_path(self, user_id: uuid.UUID) -> Path:
        user_path = self.storage_path / str(user_id)
        user_path.mkdir(parents=True, exist_ok=True)
        return user_path

    def _generate_filename(self, extension: str = ".jpg") -> str:
        """Generate a unique filename."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{timestamp}_{unique_id}{extension}"

    def _convert_heic(self, image_data: bytes) -> Image.Image:
        """Convert HEIC/HEIF to PIL Image."""
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass

        return Image.open(BytesIO(image_data))

    def _resize_image(
        self,
        image: Image.Image,
        max_size: tuple[int, int],
        quality: int = 92,
    ) -> bytes:
        """Resize image maintaining aspect ratio."""
        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if image.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize maintaining aspect ratio
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save to bytes
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

    async def process_and_store(
        self,
        user_id: uuid.UUID,
        image_data: bytes,
        original_filename: str,
    ) -> dict[str, str]:
        """
        Process an uploaded image and store all sizes.

        Returns dict with paths for each size:
        {
            "original": "user_id/20240116_123456_abc123.jpg",
            "medium": "user_id/20240116_123456_abc123_medium.jpg",
            "thumbnail": "user_id/20240116_123456_abc123_thumb.jpg",
        }
        """
        # Validate file extension
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        # Load image
        if ext in (".heic", ".heif"):
            image = self._convert_heic(image_data)
        else:
            image = Image.open(BytesIO(image_data))

        # Generate base filename
        base_filename = self._generate_filename(".jpg")
        base_name = base_filename.rsplit(".", 1)[0]

        user_path = self._get_user_path(user_id)
        paths = {}

        # Process and save each size
        for size_name, max_size in SIZES.items():
            if size_name == "original":
                suffix = ""
                quality = 95  # Highest quality for original
            elif size_name == "medium":
                suffix = "_medium"
                quality = 90
            else:
                suffix = "_thumb"
                quality = 88  # Good quality for thumbnails

            filename = f"{base_name}{suffix}.jpg"
            file_path = user_path / filename

            # For original, preserve as much quality as possible
            # For others, resize with appropriate quality
            resized_data = self._resize_image(image.copy(), max_size, quality=quality)
            file_path.write_bytes(resized_data)

            # Store relative path
            paths[size_name] = f"{user_id}/{filename}"

        # Compute perceptual hash for duplicate detection
        image_hash = self.compute_phash(image_data, original_filename)

        return {
            "image_path": paths["original"],
            "medium_path": paths["medium"],
            "thumbnail_path": paths["thumbnail"],
            "image_hash": image_hash,
        }

    def get_image_path(self, relative_path: str) -> Path:
        """Get full path for an image."""
        return self.storage_path / relative_path

    def delete_images(self, paths: dict[str, str | None]) -> None:
        """Delete all image files for an item."""
        for path in paths.values():
            if path:
                full_path = self.storage_path / path
                if full_path.exists():
                    full_path.unlink()

    def validate_image(self, image_data: bytes, content_type: str) -> bool:
        """Validate image data and content type."""
        # Check content type
        if content_type not in ALLOWED_MIME_TYPES:
            return False

        # Check file size (max 20MB)
        if len(image_data) > 20 * 1024 * 1024:
            return False

        # Try to open as image
        try:
            if content_type in ("image/heic", "image/heif"):
                self._convert_heic(image_data)
            else:
                Image.open(BytesIO(image_data))
            return True
        except Exception:
            return False

    def compute_phash(self, image_data: bytes, original_filename: str) -> str:
        """
        Compute perceptual hash (pHash) for an image.

        Returns a 16-character hex string representing the 64-bit hash.
        """
        ext = Path(original_filename).suffix.lower()

        if ext in (".heic", ".heif"):
            image = self._convert_heic(image_data)
        else:
            image = Image.open(BytesIO(image_data))

        # Convert to RGB if needed for consistent hashing
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Compute perceptual hash
        phash = imagehash.phash(image)
        return str(phash)

    def compute_phash_from_path(self, image_path: Path) -> str:
        """Compute pHash from a file path."""
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        phash = imagehash.phash(image)
        return str(phash)

    @staticmethod
    def hash_distance(hash1: str, hash2: str) -> int:
        """
        Compute Hamming distance between two hashes.

        Lower distance = more similar images.
        Distance 0 = identical/near-identical images.
        Distance < 10 = very similar images.
        """
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2

    @staticmethod
    def is_duplicate(hash1: str, hash2: str, threshold: int = 8) -> bool:
        """
        Check if two images are duplicates based on hash distance.

        Default threshold of 8 catches near-identical images while allowing
        for minor differences in lighting/compression.
        """
        return ImageService.hash_distance(hash1, hash2) <= threshold

    def remove_background(
        self,
        image_path: str,
        bg_color: tuple[int, int, int] = (255, 255, 255),
    ) -> dict[str, str]:
        from app.services.background_removal import get_provider

        base_path = image_path.rsplit(".", 1)[0]

        original_full = self.storage_path / image_path
        medium_path = f"{base_path}_medium.jpg"
        medium_full = self.storage_path / medium_path
        thumb_path = f"{base_path}_thumb.jpg"
        thumb_full = self.storage_path / thumb_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        image = Image.open(original_full).convert("RGB")
        provider = get_provider()
        result = provider.remove(image)

        # Composite onto solid color background
        background = Image.new("RGBA", result.size, (*bg_color, 255))
        background.paste(result, mask=result.split()[3])
        final = background.convert("RGB")

        for size_name, max_size in SIZES.items():
            if size_name == "original":
                file_path = original_full
                quality = 95
            elif size_name == "medium":
                file_path = medium_full
                quality = 90
            else:
                file_path = thumb_full
                quality = 88

            img_copy = final.copy()
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            img_copy.save(output, format="JPEG", quality=quality, optimize=True)
            file_path.write_bytes(output.getvalue())

        return {
            "image_path": image_path,
            "medium_path": medium_path,
            "thumbnail_path": thumb_path,
        }

    def rotate_image(self, image_path: str, direction: str = "cw") -> dict[str, str]:
        """
        Rotate an image and regenerate all sizes.

        Args:
            image_path: Relative path to the original image (e.g., "user_id/filename.jpg")
            direction: "cw" for clockwise 90°, "ccw" for counter-clockwise 90°

        Returns:
            dict with updated paths (same as input since we overwrite)
        """
        # Parse paths from original
        # Original: user_id/filename.jpg
        # Medium: user_id/filename_medium.jpg
        # Thumbnail: user_id/filename_thumb.jpg
        base_path = image_path.rsplit(".", 1)[0]  # Remove extension

        original_full = self.storage_path / image_path
        medium_path = f"{base_path}_medium.jpg"
        medium_full = self.storage_path / medium_path
        thumb_path = f"{base_path}_thumb.jpg"
        thumb_full = self.storage_path / thumb_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        # Determine rotation angle
        angle = -90 if direction == "cw" else 90  # PIL rotates counter-clockwise by default

        # Load and rotate original
        image = Image.open(original_full)

        # Convert to RGB if necessary
        if image.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Rotate
        rotated = image.rotate(angle, expand=True)

        # Save all sizes
        for size_name, max_size in SIZES.items():
            if size_name == "original":
                file_path = original_full
                quality = 95
            elif size_name == "medium":
                file_path = medium_full
                quality = 90
            else:
                file_path = thumb_full
                quality = 88

            # Resize
            img_copy = rotated.copy()
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Save
            output = BytesIO()
            img_copy.save(output, format="JPEG", quality=quality, optimize=True)
            file_path.write_bytes(output.getvalue())

        return {
            "image_path": image_path,
            "medium_path": medium_path,
            "thumbnail_path": thumb_path,
        }
