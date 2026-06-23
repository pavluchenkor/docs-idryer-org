#!/bin/bash
set -euo pipefail

: "${WEBHOOK_SECRET:?WEBHOOK_SECRET is required}"

envsubst < /app/hooks.json.template > /app/hooks.json

if [ -n "${GITHUB_TOKEN:-}" ]; then
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

exec webhook \
    -hooks /app/hooks.json \
    -port 9000 \
    -ip 0.0.0.0 \
    -verbose
