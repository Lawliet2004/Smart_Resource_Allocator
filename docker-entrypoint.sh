#!/bin/sh
# Bring the schema up to date before serving traffic, so a fresh deployment
# against an empty database does not answer requests with 500s.
#
# Set RUN_MIGRATIONS=0 if your platform runs `alembic upgrade head` as a
# separate release step (and to avoid several instances racing on boot).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
