#!/bin/sh
set -e

echo "Running Alembic migrations..."
python -m alembic upgrade head

echo "Starting aomarket-bot..."
exec python -m aomarket.main
