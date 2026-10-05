from pathlib import Path

import pytest
import yaml

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SERVICES = ("backend", "worker", "image-worker")
SETTINGS_KEYS = {name.upper() for name in Settings.model_fields}

# Read by docker-entrypoint.sh to remap appuser before the app starts, never by Settings.
ENTRYPOINT_KEYS = {"PUID", "PGID"}

# wardrobe-config is shared with the postgres and frontend Deployments, which read these.
K8S_NON_BACKEND_KEYS = {
    "POSTGRES_USER",
    "POSTGRES_DB",
    "NEXTAUTH_URL",
    "FORWARD_AUTH_LOGOUT_URL",
    "TINYAUTH_URL",
}


def _load_repo_yaml(relative_path):
    path = REPO_ROOT / relative_path
    if not path.exists():
        pytest.skip(f"{relative_path} is not available in this environment")
    return list(yaml.safe_load_all(path.read_text()))


@pytest.fixture(params=["docker-compose.yml", "docker-compose.prod.yml"])
def compose(request):
    (document,) = _load_repo_yaml(request.param)
    return document


def test_every_backend_service_merges_the_shared_env(compose):
    shared = compose["x-backend-env"]

    for name in BACKEND_SERVICES:
        env = compose["services"][name]["environment"]
        assert env.items() >= shared.items(), f"{name} must merge <<: *backend-env unchanged"


def test_notification_settings_reach_the_worker(compose):
    worker_env = compose["services"]["worker"]["environment"]

    for key in ("APP_URL", "NTFY_SERVER", "NTFY_TOPIC", "MATTERMOST_WEBHOOK_URL", "SMTP_HOST"):
        assert key in worker_env


def test_every_compose_key_is_a_setting(compose):
    for name in BACKEND_SERVICES:
        keys = set(compose["services"][name]["environment"])
        unknown = keys - SETTINGS_KEYS - ENTRYPOINT_KEYS
        assert not unknown, f"{name} passes keys no Settings field reads: {sorted(unknown)}"


def test_compose_leaves_ai_timeout_default_to_settings(compose):
    assert compose["x-backend-env"]["AI_TIMEOUT"] == "${AI_TIMEOUT:-}"


def _k8s_container(filename):
    deployment = next(
        doc for doc in _load_repo_yaml(f"k8s/{filename}") if doc and doc["kind"] == "Deployment"
    )
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    return container


def test_k8s_backend_deployments_load_the_whole_configmap():
    for filename in ("backend.yaml", "worker.yaml", "image-worker.yaml"):
        container = _k8s_container(filename)
        assert {"configMapRef": {"name": "wardrobe-config"}} in container.get("envFrom", [])
        assert not any(
            "configMapKeyRef" in entry.get("valueFrom", {}) for entry in container["env"]
        ), f"{filename} must take ConfigMap keys through envFrom, not one key at a time"


def test_k8s_backend_deployments_share_secret_env():
    names = {
        filename: {entry["name"] for entry in _k8s_container(filename)["env"]}
        for filename in ("backend.yaml", "worker.yaml", "image-worker.yaml")
    }

    backend_only = {"OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "FORWARD_AUTH_SECRET"}
    assert names["backend.yaml"] - backend_only == names["worker.yaml"]
    assert names["image-worker.yaml"] - {"BG_REMOVAL_API_KEY"} == names["worker.yaml"]


def test_every_k8s_configmap_key_is_read():
    (configmap,) = _load_repo_yaml("k8s/configmap.yaml")

    unknown = set(configmap["data"]) - SETTINGS_KEYS - ENTRYPOINT_KEYS - K8S_NON_BACKEND_KEYS
    assert not unknown, f"wardrobe-config holds keys nothing reads: {sorted(unknown)}"
