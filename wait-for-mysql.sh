#!/bin/sh
set -e

HOST="${DB_HOST:-rr-db}"
PORT=3306

echo "Waiting for MySQL at $HOST:$PORT..."

# Loop until MySQL responds
while ! nc -z "$HOST" "$PORT"; do
  echo "MySQL is not ready yet... retrying in 2 seconds."
  sleep 2
done

echo "MySQL is UP!"

exec "$@"
