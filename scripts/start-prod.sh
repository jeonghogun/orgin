#!/bin/bash
set -e

echo "Running Production Start Script"

# --- Environment Variable Checks ---
# Ensure essential variables are set
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL is not set."
    exit 1
fi
# Redis is optional in Cloud Run environment
if [ -z "$REDIS_URL" ]; then
    echo "Warning: REDIS_URL is not set. Running without Redis."
fi
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is not set."
    exit 1
fi

# --- Database Migrations (Placeholder) ---
# In a real application, you would run your database migrations here.
# e.g., alembic upgrade head
echo "Running database migrations (if any)..."
# No migrations to run for now.

# --- Start Gunicorn Server ---
# Start Gunicorn server with environment variables
echo "Starting Gunicorn server..."
exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --env DEBUG=False \
    app.main:app
