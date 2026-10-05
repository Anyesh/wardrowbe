import re
from pathlib import Path

import pytest

from app.config import Settings

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _dockerfile_text():
    return DOCKERFILE.read_text()


def test_baked_rembg_model_matches_settings_default():
    match = re.search(r"^ARG BG_REMOVAL_MODEL=(\S+)\s*$", _dockerfile_text(), re.MULTILINE)

    assert match, "Dockerfile must declare `ARG BG_REMOVAL_MODEL=<model>` for the baked rembg model"
    assert match.group(1) == Settings.model_fields["bg_removal_model"].default


def test_rembg_cache_is_outside_any_home_directory():
    match = re.search(r"^ENV REMBG_HOME=(\S+)", _dockerfile_text(), re.MULTILINE)

    assert match, "Dockerfile must pin REMBG_HOME so every uid reads the same model cache"
    assert not match.group(1).startswith(("/root", "/home", "~"))


def test_model_is_baked_into_the_pinned_cache():
    text = _dockerfile_text()

    assert re.search(r"""new_session\(\s*['"]\$BG_REMOVAL_MODEL['"]\s*\)""", text), (
        "the build step must download the model named by BG_REMOVAL_MODEL, not rembg's own default"
    )


@pytest.mark.parametrize("compose_name", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_compose_default_matches_settings_default(compose_name):
    compose = Path(__file__).resolve().parents[2] / compose_name
    if not compose.exists():
        pytest.skip(f"{compose_name} is not available in this environment")

    match = re.search(r"BG_REMOVAL_MODEL:\s*\$\{BG_REMOVAL_MODEL:-([^}]+)\}", compose.read_text())

    assert match, f"{compose_name} must pass BG_REMOVAL_MODEL with a default"
    assert match.group(1) == Settings.model_fields["bg_removal_model"].default
