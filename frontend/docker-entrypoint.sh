#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    PUID="${PUID:-1001}"
    PGID="${PGID:-1001}"

    if [ "$PGID" != "$(id -g nextjs)" ]; then
        groupmod -o -g "$PGID" nodejs
    fi
    if [ "$PUID" != "$(id -u nextjs)" ]; then
        usermod -o -u "$PUID" nextjs
    fi

    # .next must stay writable by the remapped user for the prerender cache
    if [ "$(stat -c %u /app/.next)" != "$PUID" ]; then
        chown -R nextjs:nodejs /app/.next
    fi

    exec su-exec nextjs:nodejs "$@"
fi

exec "$@"
