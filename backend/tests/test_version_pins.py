import re
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"


def _python_version():
    return (BACKEND / ".python-version").read_text().strip()


def _from_tags(dockerfile: Path, image: str):
    return re.findall(rf"^FROM\s+{image}:(\S+)", dockerfile.read_text(), re.MULTILINE)


def test_python_version_file_pins_a_minor_version():
    assert re.fullmatch(r"\d+\.\d+", _python_version())


def test_backend_dockerfile_uses_the_pinned_python():
    tags = _from_tags(BACKEND / "Dockerfile", "python")

    assert tags, "backend/Dockerfile must build FROM a python:<version> image"
    for tag in tags:
        assert tag.split("-")[0] == _python_version()


def test_pyproject_targets_the_pinned_python():
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    version = _python_version()

    assert pyproject["project"]["requires-python"] == f">={version}"
    assert pyproject["tool"]["ruff"]["target-version"] == f"py{version.replace('.', '')}"


@pytest.mark.parametrize("dockerfile_name", ["Dockerfile", "Dockerfile.dev"])
def test_frontend_dockerfiles_use_the_pinned_node_major(dockerfile_name):
    dockerfile = FRONTEND / dockerfile_name
    nvmrc = FRONTEND / ".nvmrc"
    if not dockerfile.exists() or not nvmrc.exists():
        pytest.skip(f"frontend/{dockerfile_name} is not available in this environment")

    node_major = nvmrc.read_text().strip().lstrip("v").split(".")[0]
    tags = _from_tags(dockerfile, "node")

    assert tags, f"frontend/{dockerfile_name} must build FROM a node:<version> image"
    for tag in tags:
        assert tag.split("-")[0].split(".")[0] == node_major
