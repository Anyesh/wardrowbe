from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OWNER_LABEL = "wardrowbe.stack.owner"
PROJECT_LABEL = "wardrowbe.stack.project"
SCOPE_LABEL = "wardrowbe.stack.scope"


class ComposeTag:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value


class ComposeLoader(yaml.SafeLoader):
    pass


def _construct_tagged(loader, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return ComposeTag(node.tag, value)


ComposeLoader.add_constructor("!reset", _construct_tagged)
ComposeLoader.add_constructor("!override", _construct_tagged)


def _load(relative_path):
    if not (REPO_ROOT / "docker-compose.yml").exists():
        pytest.skip("compose files are not available in this environment")
    return yaml.load((REPO_ROOT / relative_path).read_text(), Loader=ComposeLoader)


def _untag(value):
    return value.value if isinstance(value, ComposeTag) else value


@pytest.fixture(scope="module")
def stack_services():
    base = _load("docker-compose.yml")["services"]
    dev = _load("docker-compose.dev.yml")["services"]
    return {name: {**base.get(name, {}), **dev.get(name, {})} for name in {*base, *dev}}


@pytest.fixture(scope="module")
def parallel():
    return _load("docker-compose.parallel.yml")["services"]


def test_every_fixed_container_name_is_reset(stack_services, parallel):
    for name, service in stack_services.items():
        if "container_name" not in service:
            continue
        override = parallel.get(name, {}).get("container_name")
        assert isinstance(override, ComposeTag) and override.tag == "!reset", (
            f"{name} keeps a fixed container_name, so a second stack collides with it"
        )


def test_every_published_port_is_replaced_and_bound_to_loopback(stack_services, parallel):
    for name, service in stack_services.items():
        if "ports" not in service:
            continue
        ports = parallel.get(name, {}).get("ports")
        assert isinstance(ports, ComposeTag), f"{name} would also publish the main stack's ports"
        for port in ports.value:
            assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port} beyond loopback"


def test_every_service_carries_the_stack_labels(stack_services, parallel):
    for name in stack_services:
        labels = parallel.get(name, {}).get("labels", {})
        assert {OWNER_LABEL, PROJECT_LABEL} <= set(labels), f"{name} has no stack labels"


def test_every_built_service_labels_its_image(stack_services, parallel):
    built = {name for name, service in stack_services.items() if "build" in service}

    for name in built:
        service = parallel.get(name, {})
        build_labels = service.get("build", {}).get("labels", {})
        assert {OWNER_LABEL, PROJECT_LABEL, SCOPE_LABEL} <= set(build_labels), (
            f"{name} image is unlabelled"
        )
        assert service.get("pull_policy") == "never", f"{name} would build or pull on its own"
        assert "STACK_" in _untag(service.get("image", "")), f"{name} shares the main dev tag"


def test_every_volume_and_the_network_carry_the_stack_labels():
    declared = {
        *_load("docker-compose.yml").get("volumes", {}),
        *_load("docker-compose.dev.yml").get("volumes", {}),
    }
    parallel = _load("docker-compose.parallel.yml")

    for name in declared:
        labels = (parallel.get("volumes", {}).get(name) or {}).get("labels", {})
        assert {OWNER_LABEL, PROJECT_LABEL} <= set(labels), f"volume {name} has no stack labels"
    network_labels = parallel["networks"]["default"]["labels"]
    assert {OWNER_LABEL, PROJECT_LABEL} <= set(network_labels)
