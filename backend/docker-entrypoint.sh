#!/bin/sh
set -e

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

    # rembg saves a downloaded model 0600 for the uid that fetched it, so a persisted models
    # volume would stay unreadable after a PUID change. find skips entries already readable,
    # which keeps a read-only mount of complete models startable.
    models="${REMBG_HOME:-/opt/rembg}/models"
    if [ -d "$models" ]; then
        find "$models" \( -type d ! -perm -a+rx -o -type f ! -perm -a+r \) -exec chmod a+rX {} +
    fi

    exec gosu appuser "$@"
fi

exec "$@"
