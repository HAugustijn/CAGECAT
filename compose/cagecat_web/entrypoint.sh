#!/bin/sh
# Configure cblaster (NCBI requires a contact e-mail for remote searches) from
# environment variables, then run the container's command. Both values are
# optional; set CBLASTER_EMAIL in your .env to enable remote cblaster searches.
set -e

if [ -n "${CBLASTER_EMAIL:-}" ]; then
  if [ -n "${CBLASTER_API_KEY:-}" ]; then
    cblaster config --email "$CBLASTER_EMAIL" --api_key "$CBLASTER_API_KEY" >/dev/null 2>&1 || true
  else
    cblaster config --email "$CBLASTER_EMAIL" >/dev/null 2>&1 || true
  fi
fi

exec "$@"
