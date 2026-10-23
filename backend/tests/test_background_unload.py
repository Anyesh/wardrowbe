"""The image worker frees the background-removal model after a while without photos."""

import time
from unittest.mock import MagicMock, patch

from PIL import Image

from app.services.background_removal import RembgProvider


class TestBackgroundModelUnload:
    def test_the_session_is_dropped_after_idle_time(self):
        provider = RembgProvider(model="u2net", idle_seconds=0.05)
        fake = MagicMock(new_session=MagicMock(return_value="session"), remove=MagicMock())
        with patch.dict("sys.modules", {"rembg": fake}):
            provider.remove(Image.new("RGB", (4, 4)))
            assert provider._session == "session"
            time.sleep(0.3)
        assert provider._session is None
