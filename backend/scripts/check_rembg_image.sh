#!/bin/sh
set -eu

image="${1:?usage: check_rembg_image.sh <image>}"
uid=568
gid=568

model="$(docker run --rm --entrypoint python "$image" -c \
    'from app.config import Settings; print(Settings().bg_removal_model)')"
echo "configured model: $model"

load='
import os, sys, time
start = time.time()
from rembg import new_session
new_session(sys.argv[1])
cache = os.environ["NUMBA_CACHE_DIR"]
written = [
    os.path.join(d, f)
    for d, _, files in os.walk(cache)
    for f in files
    if os.path.getmtime(os.path.join(d, f)) >= start
]
if written:
    sys.exit(f"numba recompiled into {cache} instead of using the baked cache: {written[:3]}")
print("loaded", sys.argv[1], "from the baked numba cache in", round(time.time() - start), "s")
'

echo "direct non-root uid, no network"
docker run --rm --network none --user "$uid:$gid" "$image" python -c "$load" "$model"

echo "root entrypoint remapped to PUID/PGID, no network"
docker run --rm --network none -e PUID="$uid" -e PGID="$gid" "$image" python -c "$load" "$model"

volumes=""
trap 'for v in $volumes; do docker volume rm -f "$v" >/dev/null; done' EXIT
new_volume() {
    v="rembg-check-$$-$1"
    docker volume create "$v" >/dev/null
    volumes="$volumes $v"
    echo "$v"
}

echo "a model another uid downloaded into a persisted models volume, used after a PUID change"
volume="$(new_volume downloaded)"
docker run --rm --network none --user 1001:1001 -v "$volume:/opt/rembg/models" \
    --entrypoint sh "$image" -c \
    'mkdir /opt/rembg/models/other /opt/rembg/models/partial && echo x > /opt/rembg/models/other/other.onnx && chmod 600 /opt/rembg/models/other/other.onnx'
docker run --rm --network none -e PUID="$uid" -e PGID="$gid" -v "$volume:/opt/rembg/models" \
    "$image" sh -c 'cat /opt/rembg/models/other/other.onnx >/dev/null && touch /opt/rembg/models/partial/partial.onnx'
echo "readable, and an interrupted download can be resumed"

# Docker copies the image's models into a named volume only while it is empty, so a volume an
# older image seeded must still get the models this image bakes.
echo "a models volume seeded by an image that baked a different model, no network"
volume="$(new_volume stale)"
docker run --rm --network none -v "$volume:/seed" --entrypoint sh "$image" -c \
    'chmod 1777 /seed && ln -s /opt/rembg/baked/retired /seed/retired'
docker run --rm --network none -e PUID="$uid" -e PGID="$gid" -v "$volume:/opt/rembg/models" \
    "$image" sh -c 'test ! -L /opt/rembg/models/retired && python -c "$1" "$2"' sh "$load" "$model"

echo "an empty writable models volume under a direct non-root uid, no network"
volume="$(new_volume empty)"
docker run --rm --network none -v "$volume:/seed" --entrypoint sh "$image" -c \
    'chmod 1777 /seed && touch /seed/.keep'
docker run --rm --network none --user "$uid:$gid" -v "$volume:/opt/rembg/models" \
    "$image" python -c "$load" "$model"

echo "a root-owned link to a retired model in a sticky volume, direct non-root uid, no network"
volume="$(new_volume sticky)"
docker run --rm --network none -v "$volume:/seed" --entrypoint sh "$image" -c \
    'chmod 1777 /seed && ln -s /opt/rembg/baked/retired /seed/retired'
docker run --rm --network none --user "$uid:$gid" -v "$volume:/opt/rembg/models" \
    "$image" python -c "$load" "$model"

echo "a dangling link named after the baked model, no network"
volume="$(new_volume dangling)"
docker run --rm --network none -v "$volume:/seed" --entrypoint sh "$image" -c \
    "chmod 1777 /seed && ln -s /nonexistent /seed/$model"
docker run --rm --network none -e PUID="$uid" -e PGID="$gid" -v "$volume:/opt/rembg/models" \
    "$image" python -c "$load" "$model"
