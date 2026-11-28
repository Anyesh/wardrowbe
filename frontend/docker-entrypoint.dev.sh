#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    PUID="${PUID:-1000}"
    PGID="${PGID:-1000}"

    if [ "$PGID" != "$(id -g node)" ]; then
        groupmod -o -g "$PGID" node
    fi
    if [ "$PUID" != "$(id -u node)" ]; then
        usermod -o -u "$PUID" node
    fi

    # A fresh worktree has no .next in the bind mount, and stat below would fail under set -e.
    mkdir -p /app/.next
    for dir in /app/node_modules /app/.next; do
        if [ "$(stat -c %u "$dir")" != "$PUID" ]; then
            chown -R node:node "$dir"
        fi
    done

    export HOME=/home/node
    exec su-exec node:node "$@"
fi

exec "$@"
