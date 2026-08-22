from io import BytesIO

import pytest
from PIL import Image

from app.models.user import User
from app.services.image_service import ImageService

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
