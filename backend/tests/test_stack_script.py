import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_SCRIPT = REPO_ROOT / "scripts" / "stack"

FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >>"$FAKE/log"
if [ -f "$FAKE/engine-down" ]; then
    echo "Cannot connect to the Docker daemon" >&2
    exit 1
fi
case "$1 $2" in
    "ps -aq") [ -f "$FAKE/ps-fails" ] && { echo "listing failed" >&2; exit 1; } ;;
    "image ls") cat "$FAKE/images" 2>/dev/null ;;
    "image inspect") cat "$FAKE/tags/${@: -1}" ;;
    "rmi "*) [ -f "$FAKE/rmi-fails" ] && { echo "image is in use" >&2; exit 1; } ;;
esac
exit 0
"""


@pytest.fixture
def fake(tmp_path):
    fake_dir = tmp_path / "fake"
    bin_dir = fake_dir / "bin"
    (fake_dir / "tags").mkdir(parents=True)
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "ssh").write_text('#!/usr/bin/env bash\ncat "$FAKE/ssh-out" 2>/dev/null\nexit 0\n')
    for tool in ("docker", "ssh"):
        (bin_dir / tool).chmod(0o755)
    return fake_dir


def make_repo(path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def run_stack(repo, fake, snippet):
    env = {
        **os.environ,
        "FAKE": str(fake),
        "PATH": f"{fake / 'bin'}:{os.environ['PATH']}",
    }
    return subprocess.run(
        ["bash", "-c", f'source "{STACK_SCRIPT}"; {snippet}'],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


def register(repo, fake, worktree, host=""):
    result = run_stack(
        repo,
        fake,
        f'dir="$REG/$(project_for "{worktree}")"; '
        f'write_entry "$dir" "{worktree}" "{host}" "$(slug_for "{worktree}")" 1; echo "$dir"',
    )
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip())


def entry_value(entry, key):
    for line in (entry / "env").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise KeyError(key)


def add_image(fake, image_id, tag):
    with (fake / "images").open("a") as images:
        images.write(f"{image_id}\n")
    (fake / "tags" / image_id).write_text(f"{tag}\n")


def removed_images(fake):
    log = (fake / "log").read_text().splitlines() if (fake / "log").exists() else []
    return [line.split()[-1] for line in log if line.startswith("rmi ")]


def test_down_keeps_the_entry_when_the_engine_does_not_answer(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    entry = register(repo, fake, str(repo), host="build-host")
    (fake / "engine-down").touch()

    result = run_stack(repo, fake, f'down_entry "{entry}"')

    assert result.returncode != 0
    assert entry.is_dir()


def test_ls_reports_a_remote_stack_whose_engine_does_not_answer(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    entry = register(repo, fake, str(repo), host="build-host")
    (fake / "engine-down").touch()

    result = run_stack(repo, fake, "cmd_ls")

    assert result.returncode == 0, result.stderr
    row = next(line for line in result.stdout.splitlines() if line.startswith(entry.name))
    assert "unreachable" in row


def test_reap_warns_when_a_registered_host_engine_does_not_answer(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    run_stack(repo, fake, "lock; register_host build-host")
    (fake / "engine-down").touch()

    result = run_stack(repo, fake, "reap")

    assert "build-host is unreachable" in result.stderr


def test_down_keeps_the_entry_when_listing_leftovers_fails(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    entry = register(repo, fake, str(repo), host="build-host")
    (fake / "ps-fails").touch()

    result = run_stack(repo, fake, f'down_entry "{entry}"')

    assert result.returncode != 0
    assert entry.is_dir()


@pytest.mark.parametrize(
    "listing",
    [
        "  TCP    0.0.0.0:3101    0.0.0.0:0    LISTENING\r\n"
        "  TCP    [::]:8101    [::]:0    LISTENING\r\n"
        "  UDP    0.0.0.0:5353    *:*\r\n",
        "State  Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
        "LISTEN 0      4096   127.0.0.1:3101     0.0.0.0:*\n"
        "LISTEN 0      4096   [::]:8101          [::]:*\n",
        "tcp        0      0 127.0.0.1:3101          0.0.0.0:*               LISTEN\n"
        "tcp6       0      0 :::8101                 :::*                    LISTEN\n",
    ],
    ids=["windows-netstat", "linux-ss", "linux-netstat"],
)
def test_remote_listening_ports_reads_windows_and_linux_hosts(tmp_path, fake, listing):
    repo = make_repo(tmp_path / "repo")
    (fake / "ssh-out").write_text(listing)

    result = run_stack(repo, fake, "remote_listening_ports build-host")

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["3101", "8101"]


def test_down_removes_the_entry_when_teardown_succeeds(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    entry = register(repo, fake, str(repo), host="build-host")

    result = run_stack(repo, fake, f'down_entry "{entry}"')

    assert result.returncode == 0, result.stderr
    assert not entry.exists()


def test_down_leaves_shared_local_images_to_prune(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    entry = register(repo, fake, str(repo))

    result = run_stack(repo, fake, f'down_entry "{entry}"')

    assert result.returncode == 0, result.stderr
    compose_calls = [
        line for line in (fake / "log").read_text().splitlines() if line.startswith("compose ")
    ]
    assert compose_calls
    assert not any("--rmi" in line for line in compose_calls)


def test_prune_keeps_images_of_every_registered_stack(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    other = make_repo(tmp_path / "other-worktree")
    mine = register(repo, fake, str(repo))
    building = register(repo, fake, str(other))
    add_image(fake, "sha256:mine", entry_value(mine, "STACK_BACKEND_IMAGE"))
    add_image(fake, "sha256:building", "wardrowbe-backend:dev-otherdeps")
    add_image(fake, "sha256:stale", "wardrowbe-backend:dev-stale")
    (building / "env").write_text(
        (building / "env")
        .read_text()
        .replace(
            f"STACK_BACKEND_IMAGE={entry_value(building, 'STACK_BACKEND_IMAGE')}",
            "STACK_BACKEND_IMAGE=wardrowbe-backend:dev-otherdeps",
        )
    )

    result = run_stack(repo, fake, "prune_host_images")

    assert result.returncode == 0, result.stderr
    assert removed_images(fake) == ["sha256:stale"]


def test_prune_continues_when_an_image_cannot_be_removed(tmp_path, fake):
    repo = make_repo(tmp_path / "repo")
    add_image(fake, "sha256:raced", "wardrowbe-backend:dev-raced")
    add_image(fake, "sha256:stale", "wardrowbe-backend:dev-stale")
    (fake / "rmi-fails").touch()

    result = run_stack(repo, fake, "prune_host_images; echo finished")

    assert result.returncode == 0, result.stderr
    assert "finished" in result.stdout
    assert removed_images(fake) == ["sha256:raced", "sha256:stale"]


def test_checkouts_sharing_a_worktree_name_get_separate_projects_and_images(tmp_path, fake):
    first = make_repo(tmp_path / "machine-a" / "wardrowbe-stacks")
    second = make_repo(tmp_path / "machine-b" / "wardrowbe-stacks")

    entries = [register(repo, fake, str(repo), host="build-host") for repo in (first, second)]

    assert entries[0].name != entries[1].name
    for key in ("COMPOSE_PROJECT_NAME", "STACK_BACKEND_IMAGE", "STACK_FRONTEND_IMAGE"):
        assert entry_value(entries[0], key) != entry_value(entries[1], key)
    assert entry_value(entries[0], "STACK_SLUG") == entry_value(entries[1], "STACK_SLUG")
