from io import BytesIO

import imagehash
import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.models.user import User
from app.services import image_service as image_service_module
from app.services.image_service import ImageService, ImageTooLargeError


def _jpeg(size: tuple[int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (120, 60, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _photo_like_jpeg(size: tuple[int, int]) -> bytes:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for i in range(0, width, max(1, width // 12)):
        draw.ellipse(
            [i, i // 2, i + width // 3, i // 2 + height // 3],
            fill=(i % 256, (i * 3) % 256, 200),
        )
    image = image.filter(ImageFilter.GaussianBlur(radius=width / 80))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _png(size: tuple[int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (120, 60, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def tiny_pixel_ceiling(monkeypatch):
    settings = image_service_module.settings
    monkeypatch.setattr(settings, "max_image_megapixels", 0.1, raising=False)
    return settings


class TestPixelCeiling:
    @pytest.mark.asyncio
    async def test_oversized_image_is_rejected(self, test_user: User, tiny_pixel_ceiling):
        svc = ImageService()

        with pytest.raises(ImageTooLargeError) as excinfo:
            await svc.process_and_store(
                user_id=test_user.id,
                image_data=_png((800, 800)),
                original_filename="huge.png",
            )

        assert "0.6" in str(excinfo.value)
        assert "0.1" in str(excinfo.value)

    def test_rejection_is_a_value_error(self):
        assert issubclass(ImageTooLargeError, ValueError)

    @pytest.mark.asyncio
    async def test_image_at_the_ceiling_is_accepted(self, test_user: User, tiny_pixel_ceiling):
        svc = ImageService()

        paths = await svc.process_and_store(
            user_id=test_user.id,
            image_data=_png((300, 300)),
            original_filename="ok.png",
        )

        assert Image.open(svc.get_image_path(paths["image_path"])).size == (300, 300)

    def test_phash_rejects_oversized_image(self, tiny_pixel_ceiling):
        svc = ImageService()

        with pytest.raises(ImageTooLargeError):
            svc.compute_phash(_png((800, 800)), "huge.png")

    @pytest.mark.asyncio
    async def test_ceiling_applies_after_draft_so_large_jpegs_still_load(
        self, test_user: User, monkeypatch
    ):
        # A JPEG that is over the ceiling at native resolution but under it once
        # the draft decode has scaled it down must still be accepted, because the
        # oversized buffer is never allocated.
        monkeypatch.setattr(image_service_module, "SIZES", {"original": (100, 100)})
        monkeypatch.setattr(image_service_module.settings, "max_image_megapixels", 0.2)
        svc = ImageService()

        image = svc._open_bounded(_jpeg((800, 800)), ".jpg")

        assert image.size[0] * image.size[1] <= 0.2 * 1_000_000


class TestDraftDecode:
    def test_jpeg_is_drafted_down_before_decode(self, monkeypatch):
        monkeypatch.setattr(image_service_module, "SIZES", {"original": (300, 300)})
        svc = ImageService()

        image = svc._open_bounded(_jpeg((1200, 1200)), ".jpg")

        assert image.size == (300, 300)

    def test_draft_never_undershoots_the_target_size(self, monkeypatch):
        monkeypatch.setattr(image_service_module, "SIZES", {"original": (300, 300)})
        svc = ImageService()

        image = svc._open_bounded(_jpeg((1000, 700)), ".jpg")

        assert image.size[0] >= 300
        assert image.size[1] >= 300

    def test_png_is_not_drafted(self, monkeypatch):
        monkeypatch.setattr(image_service_module, "SIZES", {"original": (300, 300)})
        svc = ImageService()

        image = svc._open_bounded(_png((1200, 1200)), ".png")

        assert image.size == (1200, 1200)

    def test_hash_is_unchanged_for_sources_the_draft_does_not_reduce(self):
        # Duplicate detection compares new uploads against hashes stored before
        # the draft decode existed. Draft only reduces once both dimensions are
        # at least twice SIZES["original"], so for every ordinary camera photo
        # the stored hash must stay bit-identical.
        data = _photo_like_jpeg((4032, 3024))
        full_res = Image.open(BytesIO(data)).convert("RGB")

        drafted = ImageService()._open_bounded(data, ".jpg")

        assert drafted.size == full_res.size
        assert ImageService()._phash_of(drafted) == str(imagehash.phash(full_res))

    def test_hash_survives_a_draft_that_does_reduce(self):
        # Above the draft threshold the hash is computed from a DCT-scaled
        # decode rather than the native buffer. That is lossy for synthetic
        # high-frequency patterns, but photographic content stays inside
        # is_duplicate's threshold, which is what the heuristic needs.
        data = _photo_like_jpeg((9600, 7200))
        full_res = Image.open(BytesIO(data)).convert("RGB")

        drafted = ImageService()._open_bounded(data, ".jpg")

        assert drafted.size == (4800, 3600)
        assert ImageService.is_duplicate(
            str(imagehash.phash(full_res)), ImageService()._phash_of(drafted)
        )

    @pytest.mark.asyncio
    async def test_drafted_upload_still_stores_correct_dimensions(self, test_user: User):
        svc = ImageService()

        paths = await svc.process_and_store(
            user_id=test_user.id,
            image_data=_jpeg((4800, 3600)),
            original_filename="big.jpg",
        )

        assert Image.open(svc.get_image_path(paths["image_path"])).size == (2400, 1800)
        assert Image.open(svc.get_image_path(paths["medium_path"])).size == (800, 600)
        assert Image.open(svc.get_image_path(paths["thumbnail_path"])).size == (400, 300)


class TestSaveAllSizesResizesFromSource:
    def test_every_variant_is_resized_from_the_full_image(self, tmp_path):
        # SIZES iterates smallest first, so a progressive resize (each pass
        # feeding the next) would silently write medium and original at
        # thumbnail size. Each pass must start from a fresh copy of the source.
        svc = ImageService(storage_path=str(tmp_path))
        source = Image.new("RGB", (2000, 2000), (10, 200, 30))
        (tmp_path / "u").mkdir()

        paths = svc._save_all_sizes(source, "u/item.jpg")

        assert Image.open(tmp_path / paths["image_path"]).size == (2000, 2000)
        assert Image.open(tmp_path / paths["medium_path"]).size == (800, 800)
        assert Image.open(tmp_path / paths["thumbnail_path"]).size == (400, 400)
