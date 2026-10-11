#!/bin/sh
set -e

# A models volume keeps whatever the image that first seeded it baked, so links to models this
# image no longer bakes are dropped (rembg cannot create a model dir over a dangling link) and
# models it does bake are linked in. Skipped when the dir is not writable, e.g. a read-only mount.
# Failures only warn, because a stale cache entry must not keep the worker from starting.
link_baked_models() {
    home="${REMBG_HOME:-/opt/rembg}"
    if [ ! -d "$home/models" ] || [ ! -w "$home/models" ]; then
        return 0
    fi
    for entry in "$home/models"/*; do
        if [ -L "$entry" ] && [ ! -e "$entry" ]; then
            case "$(readlink "$entry")" in
                "$home/baked"/*) ;;
                *) [ -d "$home/baked/${entry##*/}" ] || continue ;;
            esac
            rm -f "$entry" ||
                echo "warning: cannot remove stale link $entry; delete it, or background removal with that model fails" >&2
        fi
    done
    for baked in "$home/baked"/*; do
        target="$home/models/${baked##*/}"
        if [ -d "$baked" ] && [ ! -e "$target" ] && [ ! -L "$target" ]; then
            ln -s "$baked" "$home/models/" || echo "warning: cannot link baked model $baked" >&2
        fi
    done
}

if [ "$(id -u)" = "0" ]; then
    PUID="${PUID:-1000}"
    PGID="${PGID:-1000}"

    if [ "$PGID" != "$(id -g appuser)" ]; then
        groupmod -o -g "$PGID" appuser
    fi
    if [ "$PUID" != "$(id -u appuser)" ]; then
        usermod -o -u "$PUID" appuser
    fi

    for dir in /data/wardrobe /data/uploads; do
        # chown only on ownership mismatch so large wardrobes don't pay a
        # recursive chown on every container start
        if [ -d "$dir" ] && [ "$(stat -c %u "$dir")" != "$PUID" ]; then
            chown -R appuser:appuser "$dir"
        fi
    done

    link_baked_models
    # rembg saves a model 0600 in a 0755 dir owned by the uid that downloaded it, so after a PUID
    # change a persisted model is unreadable and an interrupted download cannot be resumed.
    # -h changes a link itself, never the file it points to.
    models="${REMBG_HOME:-/opt/rembg}/models"
    if [ -d "$models" ] && [ -w "$models" ]; then
        find -H "$models" -mindepth 1 ! -user "$PUID" -exec chown -h appuser:appuser {} + ||
            echo "warning: cannot hand $models to PUID $PUID" >&2
    fi

    exec gosu appuser "$@"
fi

link_baked_models
exec "$@"
