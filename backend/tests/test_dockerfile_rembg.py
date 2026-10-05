import re
from pathlib import Path

import pytest

from app.config import Settings

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _dockerfile_text():
    return DOCKERFILE.read_text()


def _instructions():
    joined = re.sub(r"\\\n", " ", _dockerfile_text())
    lines = [line.strip() for line in joined.splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _env_index(name):
    for index, line in enumerate(_instructions()):
        if line.startswith("ENV "):
            match = re.search(rf"(?:^ENV |\s){name}=(\S+)", line)
            if match:
                return index, match.group(1)
    return None, None


def test_baked_rembg_model_matches_settings_default():
    match = re.search(r"^ARG BG_REMOVAL_MODEL=(\S+)\s*$", _dockerfile_text(), re.MULTILINE)

    assert match, "Dockerfile must declare `ARG BG_REMOVAL_MODEL=<model>` for the baked rembg model"
    assert match.group(1) == Settings.model_fields["bg_removal_model"].default


def test_rembg_cache_is_outside_any_home_directory():
    _, rembg_home = _env_index("REMBG_HOME")

    assert rembg_home, "Dockerfile must pin REMBG_HOME so every uid reads the same model cache"
    assert not rembg_home.startswith(("/root", "/home", "~"))


def test_model_is_baked_into_the_pinned_cache():
    text = _dockerfile_text()

    assert re.search(r"""new_session\(\s*['"]\$BG_REMOVAL_MODEL['"]\s*\)""", text), (
        "the build step must download the model named by BG_REMOVAL_MODEL, not rembg's own default"
    )


def test_numba_cache_is_baked_portably_before_the_model_step():
    bake = next(
        index
        for index, line in enumerate(_instructions())
        if line.startswith("RUN ") and "new_session" in line
    )
    cache_index, cache_dir = _env_index("NUMBA_CACHE_DIR")
    cpu_index, cpu_name = _env_index("NUMBA_CPU_NAME")

    # numba keys cache entries by host CPU, and CI on one runner cannot notice a miss on another
    assert cpu_name == "generic"
    assert cache_dir and not cache_dir.startswith(("/root", "/home", "~", "/tmp"))
    assert cache_index < bake and cpu_index < bake


@pytest.mark.parametrize("compose_name", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_compose_default_matches_settings_default(compose_name):
    compose = Path(__file__).resolve().parents[2] / compose_name
    if not compose.exists():
        pytest.skip(f"{compose_name} is not available in this environment")

    match = re.search(r"BG_REMOVAL_MODEL:\s*\$\{BG_REMOVAL_MODEL:-([^}]+)\}", compose.read_text())

    assert match, f"{compose_name} must pass BG_REMOVAL_MODEL with a default"
    assert match.group(1) == Settings.model_fields["bg_removal_model"].default
