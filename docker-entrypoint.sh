#!/bin/bash
# Railway/Docker entrypoint — validates config and starts the app
set -e

export PORT="${PORT:-8000}"

# Pre-flight validation in production
if [ "$WEEKLYAMP_ENV" = "production" ] || [ "$WEEKLYAMP_ENV" = "prod" ]; then
    echo "Production mode — validating configuration..."

    if [ -z "$WEEKLYAMP_SECRET_KEY" ]; then
        echo "FATAL: WEEKLYAMP_SECRET_KEY is required in production"
        exit 1
    fi

    if [ -z "$WEEKLYAMP_ADMIN_HASH" ] && [ -z "$WEEKLYAMP_ADMIN_PASSWORD" ]; then
        echo "FATAL: WEEKLYAMP_ADMIN_HASH or WEEKLYAMP_ADMIN_PASSWORD is required in production"
        exit 1
    fi

    echo "Configuration validated."
fi

echo "Starting TrueFans NEWSLETTERS on port $PORT"
exec python /app/start.py
