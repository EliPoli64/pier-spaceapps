#!/bin/sh
# 10-listen-on-ipv6-by-default.sh runs before 20-envsubst-on-templates.sh, which
# overwrites /etc/nginx/conf.d/default.conf from default.conf.template. Add the
# IPv6 listener on the resolved $PORT afterward whenever IPv6 is enabled.
set -eu

CONF="/etc/nginx/conf.d/default.conf"
PORT="${PORT:-80}"

if [ ! -f /proc/net/if_inet6 ] || [ ! -f "$CONF" ]; then
    exit 0
fi

if ! grep -qE "^[[:space:]]*listen[[:space:]]+\[::\]:" "$CONF"; then
    awk -v port="$PORT" '
        {
            print
            if (!added && $0 ~ "^[[:space:]]*listen[[:space:]]+" port ";") {
                match($0, /^[[:space:]]*/)
                indent = substr($0, RSTART, RLENGTH)
                print indent "listen [::]:" port ";"
                added = 1
            }
        }
    ' "$CONF" > "${CONF}.tmp" && mv "${CONF}.tmp" "$CONF"
    echo "25-listen-on-ipv6.sh: info: Enabled listen on IPv6 port ${PORT} in $CONF"
fi
