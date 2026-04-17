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

    # Admin credentials can also come from the DB (admin_settings table,
    # populated by the in-app change-password UI). That check requires a
    # DB connection which we can't do safely from a shell script, so we
    # defer admin-credential validation to the Python preflight in
    # create_app() — it knows how to check both env vars AND the DB.
    # Here we only enforce SECRET_KEY, which must be an env var.

    echo "Configuration validated."
fi

echo "Starting TrueFans SIGNAL on port $PORT"
exec python /app/start.py
