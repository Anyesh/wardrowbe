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

    exec gosu appuser "$@"
fi

exec "$@"
