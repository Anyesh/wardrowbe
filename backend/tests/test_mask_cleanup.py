from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.services.mask_cleanup import NoGarmentFound, clean_cutout

SHIRT = (200, 40, 40)


def _photo(size=(200, 200)) -> Image.Image:
    width, height = size
    photo = Image.new("RGB", size, (240, 240, 240))
    box = (width // 5, height // 5, width * 4 // 5, height * 4 // 5)
    ImageDraw.Draw(photo).rectangle(box, fill=SHIRT)
    return photo


def _cutout(size=(200, 200), shapes=((40, 40, 160, 160),), holes=()) -> Image.Image:
    """A provider result: transparent black outside the garment, as rembg returns it."""
    cut = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    for box in shapes:
        draw.rectangle(box, fill=(*SHIRT, 255))
    for box in holes:
        draw.rectangle(box, fill=(0, 0, 0, 0))
    return cut


class TestCleanCutout:
    def test_fills_a_print_the_model_punched_out(self):
        result = clean_cutout(_photo(), _cutout(holes=[(90, 90, 110, 110)]))

        assert result.getpixel((100, 100)) == (*SHIRT, 255)

    def test_keeps_a_large_opening(self):
        # A bag handle: the gap inside is a real opening, not fabric.
        cut = _cutout(shapes=[(20, 20, 180, 180)], holes=[(50, 50, 150, 150)])
        result = clean_cutout(_photo(), cut)

        assert result.getpixel((100, 100))[3] == 0

    def test_drops_loose_bits_of_background(self):
        cut = _cutout(shapes=[(40, 40, 160, 160), (2, 2, 6, 6)])
        result = clean_cutout(_photo(), cut)

        assert result.getpixel((4, 4))[3] == 0
        assert result.getpixel((100, 100))[3] == 255

    def test_keeps_both_shoes_of_a_pair(self):
        cut = _cutout(shapes=[(10, 60, 90, 140), (110, 70, 180, 140)])
        result = clean_cutout(_photo(), cut)

        assert result.getpixel((50, 100))[3] == 255
        assert result.getpixel((150, 100))[3] == 255

    def test_keeps_a_small_detached_part(self):
        # A strap or a hood cut off by the model: small next to the body, still fabric.
        cut = _cutout(shapes=[(40, 40, 160, 160), (170, 40, 179, 90)])
        result = clean_cutout(_photo(), cut)

        assert result.getpixel((174, 65))[3] == 255

    def test_accepts_a_small_garment(self):
        # A ring in the middle of the photo covers about 1% of it.
        result = clean_cutout(_photo(), _cutout(shapes=[(90, 90, 110, 110)]))

        assert result.getpixel((100, 100))[3] == 255

    def test_an_empty_result_keeps_the_original(self):
        with pytest.raises(NoGarmentFound):
            clean_cutout(_photo(), _cutout(shapes=[(0, 0, 3, 3)]))

    def test_a_result_of_another_size_is_scaled_to_the_photo(self):
        result = clean_cutout(_photo(), _cutout(size=(100, 100), shapes=[(20, 20, 80, 80)]))

        assert result.size == (200, 200)
        assert result.getpixel((100, 100))[3] == 255
        assert result.getpixel((5, 5))[3] == 0


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    _photo((800, 500)).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest_asyncio.fixture
async def item(db_session: AsyncSession, test_user: User) -> ClothingItem:
    paths = await ImageService().process_and_store(
        user_id=test_user.id, image_data=_jpeg_bytes(), original_filename="shirt.jpg"
    )
    item = ClothingItem(
        user_id=test_user.id,
        type="shirt",
        image_path=paths["image_path"],
        medium_path=paths["medium_path"],
        thumbnail_path=paths["thumbnail_path"],
        image_hash=paths["image_hash"],
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _recording_provider(seen: list):
    provider = MagicMock()

    def remove(img):
        seen.append(img.copy())
        return Image.new("RGBA", img.size, (0, 0, 255, 255))

    provider.remove.side_effect = remove
    return provider


class TestRedoFromOriginal:
    @pytest.mark.asyncio
    async def test_second_removal_starts_from_the_original_photo(self, item: ClothingItem):
        svc = ImageService()
        seen: list[Image.Image] = []
        with patch(
            "app.services.background_removal.get_provider", return_value=_recording_provider(seen)
        ):
            svc.remove_background(item.image_path)
            svc.remove_background(item.image_path)

        # The second run sees the red shirt again, not the first run's blue result.
        width, height = seen[1].size
        r, g, b = seen[1].getpixel((width // 2, height // 2))
        assert r > 150 and b < 100

    @pytest.mark.asyncio
    async def test_failed_removal_leaves_no_backup(self, item: ClothingItem):
        svc = ImageService()
        provider = MagicMock()
        provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (0, 0, 0, 0))
        with (
            patch("app.services.background_removal.get_provider", return_value=provider),
            pytest.raises(NoGarmentFound),
        ):
            svc.remove_background(item.image_path)

        backup = item.image_path.rsplit(".", 1)[0] + "_orig.jpg"
        assert not svc.get_image_path(backup).exists()

    @pytest.mark.asyncio
    async def test_an_interrupted_backup_write_leaves_no_backup(self, item: ClothingItem):
        svc = ImageService()
        with (
            patch(
                "app.services.background_removal.get_provider",
                return_value=_recording_provider([]),
            ),
            patch("app.services.image_service.shutil.copy2", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            svc.remove_background(item.image_path)

        backup = svc.get_image_path(item.image_path.rsplit(".", 1)[0] + "_orig.jpg")
        assert not backup.exists()
        assert not list(backup.parent.glob("*.tmp"))

    @pytest.mark.asyncio
    async def test_a_failed_rotation_leaves_the_backup_as_it_was(self, item: ClothingItem):
        svc = ImageService()
        with patch(
            "app.services.background_removal.get_provider", return_value=_recording_provider([])
        ):
            svc.remove_background(item.image_path)
        backup = svc.get_image_path(item.image_path.rsplit(".", 1)[0] + "_orig.jpg")
        before = Image.open(backup).size

        with (
            patch.object(ImageService, "_save_all_sizes", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            svc.rotate_image(item.image_path, "cw")

        # The photo was not turned, so neither is its backup.
        assert Image.open(backup).size == before

    @pytest.mark.asyncio
    async def test_rotation_turns_the_backup_too(self, item: ClothingItem):
        svc = ImageService()
        with patch(
            "app.services.background_removal.get_provider", return_value=_recording_provider([])
        ):
            result = svc.remove_background(item.image_path)
        backup_full = svc.get_image_path(result["original_backup_path"])
        with Image.open(backup_full) as before:
            width, height = before.size

        svc.rotate_image(item.image_path, "cw")

        with Image.open(backup_full) as after:
            assert after.size == (height, width)
