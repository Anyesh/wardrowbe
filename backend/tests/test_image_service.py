import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.models.item import ClothingItem
from app.models.user import User
from app.services.image_service import VARIANTS, ImageService

GREEN = (10, 200, 30)


def _jpeg_with_orientation(orientation: int, size: tuple[int, int] = (600, 400)) -> bytes:
    img = Image.new("RGB", size, GREEN)
    exif = img.getexif()
    exif[0x0112] = orientation  # EXIF Orientation tag
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class TestExifOrientation:
    @pytest.mark.asyncio
    async def test_rotated_portrait_photo_stored_upright(self, test_user: User):
        svc = ImageService()
        data = _jpeg_with_orientation(orientation=6, size=(600, 400))

        paths = await svc.process_and_store(
            user_id=test_user.id, image_data=data, original_filename="portrait.jpg"
        )

        stored = Image.open(svc.get_image_path(paths["image_path"]))
        assert stored.size == (400, 600)
        assert "exif" not in stored.info or stored.getexif().get(0x0112) in (None, 1)

    @pytest.mark.asyncio
    async def test_unrotated_photo_dimensions_unchanged(self, test_user: User):
        svc = ImageService()
        data = _jpeg_with_orientation(orientation=1, size=(600, 400))

        paths = await svc.process_and_store(
            user_id=test_user.id, image_data=data, original_filename="normal.jpg"
        )

        stored = Image.open(svc.get_image_path(paths["image_path"]))
        assert stored.size == (600, 400)


class TestVariantTable:
    def test_variant_sizes_and_qualities(self):
        assert [(v.path_field, v.suffix, v.max_px, v.quality) for v in VARIANTS] == [
            ("image_path", "", 2400, 95),
            ("medium_path", "_medium", 800, 90),
            ("thumbnail_path", "_thumb", 400, 88),
        ]

    def test_every_path_field_is_an_item_column(self):
        columns = set(ClothingItem.__table__.columns.keys())

        assert {v.path_field for v in VARIANTS} <= columns

    @pytest.mark.asyncio
    async def test_stored_variants_follow_the_table(self, test_user: User):
        svc = ImageService()
        data = _jpeg_with_orientation(orientation=1, size=(3000, 1500))

        paths = await svc.process_and_store(
            user_id=test_user.id, image_data=data, original_filename="wide.jpg"
        )

        assert paths["medium_path"].endswith("_medium.jpg")
        assert paths["thumbnail_path"].endswith("_thumb.jpg")
        for variant in VARIANTS:
            assert Image.open(svc.get_image_path(paths[variant.path_field])).size == (
                variant.max_px,
                variant.max_px // 2,
            )


class TestRegenerateThumbnailsScript:
    def test_rewrites_derived_variants_from_the_table(self, tmp_path):
        spec = importlib.util.spec_from_file_location(
            "regenerate_thumbnails",
            Path(__file__).parent.parent / "scripts" / "regenerate_thumbnails.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        original = tmp_path / "abc.jpg"
        Image.new("RGBA", (3000, 1500), (200, 10, 10, 128)).convert("RGB").save(original)

        script.regenerate_variants(ImageService(str(tmp_path)), original)

        for variant in VARIANTS[1:]:
            written = Image.open(tmp_path / f"abc{variant.suffix}.jpg")
            assert written.size == (variant.max_px, variant.max_px // 2)
        assert Image.open(original).size == (3000, 1500)
