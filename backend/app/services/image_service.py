import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import imagehash
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from app.config import get_settings
from app.services import background_removal

settings = get_settings()


@dataclass(frozen=True)
class ImageVariant:
    path_field: str
    suffix: str
    max_px: int
    quality: int

    @property
    def box(self) -> tuple[int, int]:
        return (self.max_px, self.max_px)


# Thumbnails are 400px so that ~200px cards stay sharp on retina screens.
VARIANTS = (
    ImageVariant("image_path", "", 2400, 95),
    ImageVariant("medium_path", "_medium", 800, 90),
    ImageVariant("thumbnail_path", "_thumb", 400, 88),
)
ORIGINAL = VARIANTS[0]

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}
ALLOWED_EXTENSIONS = frozenset(IMAGE_MIME_TYPES)
ALLOWED_MIME_TYPES = frozenset(IMAGE_MIME_TYPES.values())


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


class ImageTooLargeError(ValueError):
    def __init__(self, pixels: int, limit_pixels: int):
        self.pixels = pixels
        self.limit_pixels = limit_pixels
        super().__init__(
            f"Image is {pixels / 1_000_000:.1f}MP, above the {limit_pixels / 1_000_000:.1f}MP limit"
        )


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
        register_heif_opener()
        return Image.open(BytesIO(image_data))

    def _open_bounded(self, image_data: bytes, ext: str) -> Image.Image:
        """Open an upload without ever allocating a full-resolution buffer for it.

        Image.open parses only the header, and draft() picks a JPEG DCT scaling
        factor, so both run before any pixel decode. draft never scales below the
        requested box, so the variants generated afterwards are unaffected. It is
        a no-op for formats that cannot scale during decode, which is why the
        ceiling is checked on the post-draft size.
        """
        if ext in (".heic", ".heif"):
            image = self._convert_heic(image_data)
        else:
            image = Image.open(BytesIO(image_data))

        image.draft("RGB", ORIGINAL.box)

        pixels = image.size[0] * image.size[1]
        limit_pixels = int(settings.max_image_megapixels * 1_000_000)
        if pixels > limit_pixels:
            raise ImageTooLargeError(pixels, limit_pixels)

        return image

    def _encode_variant(self, image: Image.Image, variant: ImageVariant) -> bytes:
        image = _flatten_to_rgb(image.copy())
        image.thumbnail(variant.box, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=variant.quality, optimize=True)
        return output.getvalue()

    async def process_and_store(
        self,
        user_id: uuid.UUID,
        image_data: bytes,
        original_filename: str,
    ) -> dict[str, str]:
        """
        Process an uploaded image and store all sizes.

        Returns the relative path of each variant plus the pHash:
        {
            "image_path": "user_id/20240116_123456_abc123.jpg",
            "medium_path": "user_id/20240116_123456_abc123_medium.jpg",
            "thumbnail_path": "user_id/20240116_123456_abc123_thumb.jpg",
            "image_hash": "c3d4...",
        }
        """
        # Validate file extension
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        image = self._open_bounded(image_data, ext)

        # iPhones (and some Android cameras) store a raw sensor image plus an EXIF
        # orientation tag instead of rotating pixels, so portrait photos must be
        # transposed here or they end up sideways in storage and in AI tagging.
        image = ImageOps.exif_transpose(image)

        base_name = self._generate_filename(".jpg").rsplit(".", 1)[0]
        user_path = self._get_user_path(user_id)
        paths = {}

        for variant in VARIANTS:
            filename = f"{base_name}{variant.suffix}.jpg"
            (user_path / filename).write_bytes(self._encode_variant(image, variant))
            paths[variant.path_field] = f"{user_id}/{filename}"

        paths["image_hash"] = self._phash_of(image)
        return paths

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
        image = self._open_bounded(image_data, Path(original_filename).suffix.lower())
        return self._phash_of(ImageOps.exif_transpose(image))

    def _phash_of(self, image: Image.Image) -> str:
        if image.mode != "RGB":
            image = image.convert("RGB")
        return str(imagehash.phash(image))

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

    def _save_all_sizes(self, image: Image.Image, image_path: str) -> dict[str, str]:
        base_path = image_path.rsplit(".", 1)[0]
        paths = {}
        for variant in VARIANTS:
            # The original is written back to image_path itself so that the stored path stays valid.
            path = image_path if variant is ORIGINAL else f"{base_path}{variant.suffix}.jpg"
            (self.storage_path / path).write_bytes(self._encode_variant(image, variant))
            paths[variant.path_field] = path
        return paths

    def remove_background(
        self,
        image_path: str,
        bg_color: tuple[int, int, int] = (255, 255, 255),
    ) -> dict[str, str]:
        base_path = image_path.rsplit(".", 1)[0]
        original_full = self.storage_path / image_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        backup_path = f"{base_path}_orig.jpg"
        backup_full = self.storage_path / backup_path
        # First removal wins: a second removal must not overwrite the true
        # original with an already-processed image
        if not backup_full.exists():
            shutil.copy2(original_full, backup_full)

        image = Image.open(original_full).convert("RGB")
        provider = background_removal.get_provider()
        result = provider.remove(image)

        # Composite onto solid color background
        background = Image.new("RGBA", result.size, (*bg_color, 255))
        background.paste(result, mask=result.split()[3])
        final = background.convert("RGB")

        paths = self._save_all_sizes(final, image_path)
        paths["original_backup_path"] = backup_path
        return paths

    def restore_original(self, image_path: str, backup_path: str) -> dict[str, str]:
        backup_full = self.storage_path / backup_path
        if not backup_full.exists():
            raise ValueError(f"Backup not found: {backup_path}")

        image = Image.open(backup_full).convert("RGB")
        paths = self._save_all_sizes(image, image_path)
        backup_full.unlink()
        return paths

    def rotate_image(self, image_path: str, direction: str = "cw") -> dict[str, str]:
        """
        Rotate an image and regenerate all sizes.

        Args:
            image_path: Relative path to the original image (e.g., "user_id/filename.jpg")
            direction: "cw" for clockwise 90°, "ccw" for counter-clockwise 90°

        Returns:
            dict with updated paths (same as input since we overwrite)
        """
        original_full = self.storage_path / image_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        angle = -90 if direction == "cw" else 90  # PIL rotates counter-clockwise by default

        image = _flatten_to_rgb(Image.open(original_full))

        rotated = image.rotate(angle, expand=True)

        return self._save_all_sizes(rotated, image_path)
