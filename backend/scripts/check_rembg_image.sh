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
