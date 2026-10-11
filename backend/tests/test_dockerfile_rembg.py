import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
DOCKERIGNORE = DOCKERFILE.with_name(".dockerignore")


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
def test_compose_passes_the_model_and_persists_its_cache(compose_name):
    compose = Path(__file__).resolve().parents[2] / compose_name
    if not compose.exists():
        pytest.skip(f"{compose_name} is not available in this environment")
    config = yaml.safe_load(compose.read_text())
    worker = config["services"]["image-worker"]
    _, rembg_home = _env_index("REMBG_HOME")

    match = re.fullmatch(
        r"\$\{BG_REMOVAL_MODEL:-([^}]+)\}", worker["environment"].get("BG_REMOVAL_MODEL", "")
    )

    assert match, f"{compose_name} must pass BG_REMOVAL_MODEL to image-worker with a default"
    assert match.group(1) == Settings.model_fields["bg_removal_model"].default
    # A model picked at runtime is downloaded into the volume once instead of into a container
    # layer that recreation discards
    assert f"rembg_models:{rembg_home}/models" in worker["volumes"]
    assert "rembg_models" in config["volumes"]


@pytest.mark.parametrize("pattern", [".env", ".env.*", ".venv", "**/__pycache__"])
def test_build_context_leaves_out_secrets_and_local_state(pattern):
    # `COPY . .` would otherwise bake a developer's .env and virtualenv into the image
    assert DOCKERIGNORE.exists(), "backend/.dockerignore must exist"
    assert pattern in DOCKERIGNORE.read_text().split()
